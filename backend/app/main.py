import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.agent.investigate import investigate
from backend.app.api.schemas import CompareRequest, IndexRequest, SearchRequest, TraceRequest
from backend.app.config import ROOT, Settings
from backend.app.indexing.service import IndexService
from backend.app.indexing.discovery import read_snapshot, snapshot_hash
from backend.app.versions.compare import compare_indexes

# JSON bodies stay small and bounded: a full problem-statement query (MAX_QUERY_CHARS) plus escaping headroom.
MAX_BODY_BYTES = 128 * 1024

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None):
    # /docs and /redoc would load Swagger/ReDoc scripts from a CDN that the CSP below blocks; the machine-readable
    # contract stays at /openapi.json.
    app = FastAPI(title="ASTFLOW", version="0.1.0", description="Find the code. Trace the path. See what changed.",
                  docs_url=None, redoc_url=None)
    service = IndexService(settings)
    app.state.service = service
    app.state.index_lock = threading.Lock()
    app.state.change_check = {"at": 0, "key": None, "changed": False}
    app.state.change_lock = threading.Lock()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"])

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        # The local file-reading API must not be usable by arbitrary web origins.
        origin = request.headers.get("origin")
        allowed = {f"{request.url.scheme}://{request.url.netloc}", "http://127.0.0.1:5173", "http://localhost:5173"}
        if request.url.path.startswith("/api") and origin and origin not in allowed:
            return JSONResponse({"detail": "Only local ASTFLOW origins are allowed"}, status_code=403)
        if request.url.path.startswith("/api") and request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests are not allowed"}, status_code=403)
        if request.method == "POST" and request.url.path.startswith("/api"):
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "JSON content type required"}, status_code=415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BODY_BYTES:
                    return JSONResponse({"detail": "Request body is too large"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; worker-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(ValueError)
    async def invalid_request(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(FileNotFoundError)
    async def missing_file(request, exc):
        return JSONResponse({"detail": "Repository or index file does not exist"}, status_code=404)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "ASTFLOW", "version": "0.1.0", "semantic": service.embedder.status}

    @app.get("/api/repository")
    def repository(version: str | None = None):
        return service.repository(version)

    @app.post("/api/index")
    def index_repository(body: IndexRequest):
        if not app.state.index_lock.acquire(blocking=False):
            raise HTTPException(409, "An indexing job is already running")

        def build():
            try:
                return service.index(body.repo_path, body.version).manifest
            finally:
                app.state.index_lock.release()

        if body.background:
            service.status = {"state": "indexing", "stage": "Starting index", "progress": 0}

            def background_build():
                try:
                    build()
                except Exception:
                    logger.exception("Indexing failed")

            threading.Thread(target=background_build, daemon=True).start()
            return JSONResponse({"status": "indexing"}, status_code=202)
        return {"status": "ready", "manifest": build()}

    @app.get("/api/index/status")
    def index_status():
        return service.status

    @app.post("/api/search")
    def search(body: SearchRequest):
        if body.runtime_trace_id:
            raise HTTPException(400, "Runtime tracing is not enabled in this build")
        return investigate(service.get(body.version), body.query, body.version, body.top_k, body.agentic)

    @app.post("/api/trace")
    def trace(body: TraceRequest):
        index = service.get(body.version)
        return {**index.graph.trace(body.source_symbol_id, body.target_symbol_id, body.max_depth),
                "version_key": index.manifest["version_key"]}

    @app.get("/api/source")
    def source(path: str, version: str = "working-tree", start_line: int = Query(1, ge=1), end_line: int | None = Query(None, ge=1)):
        if "\\" in path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise HTTPException(400, "Source paths must be repository-relative POSIX paths")
        index = service.get(version)
        if path not in index.files:
            raise HTTPException(404, "Source file is not in this indexed snapshot")
        source_text = index.files[path]
        lines = source_text.splitlines(keepends=True)
        if not lines and start_line == 1 and end_line is None:
            return {"path": path, "version": version, "version_key": index.manifest["version_key"],
                    "start_line": 1, "end_line": 1, "total_lines": 0, "content": "", "full_content": ""}
        end = end_line if end_line is not None else len(lines)
        if start_line > len(lines) or end < start_line or end > len(lines):
            raise HTTPException(400, "Source line range is outside the file")
        return {"path": path, "version": version, "version_key": index.manifest["version_key"],
                "start_line": start_line, "end_line": end, "total_lines": len(lines),
                "content": "".join(lines[start_line - 1:end]), "full_content": source_text}

    @app.get("/api/versions")
    def versions():
        return {"versions": service.versions()}

    @app.get("/api/map")
    def map_repository(version: str = "working-tree", file: str | None = None,
                       symbol: str | None = None, depth: int = Query(1, ge=1, le=3)):
        index = service.get(version)
        if symbol:
            if symbol not in index.graph.graph:
                raise HTTPException(404, 'Unknown callable symbol')
            ids, frontier, limited = {symbol}, [symbol], False
            for _ in range(depth):
                next_frontier = []
                for current in frontier:
                    for neighbor in index.graph.neighbors(current):
                        if neighbor not in ids:
                            if len(ids) >= 150:
                                limited = True
                                continue
                            ids.add(neighbor); next_frontier.append(neighbor)
                frontier = next_frontier
            return {**index.graph.subgraph(ids), 'version_key': index.manifest['version_key'],
                    'focus_symbol': symbol, 'status': 'SEARCH_LIMIT_REACHED' if limited else 'OK',
                    'message': f'{len(ids)} symbols within {depth} call hop(s); arrows show caller to callee'}
        if file and file not in index.files:
            raise HTTPException(404, 'Source file is not in this indexed snapshot')
        if not file:
            paths = sorted(index.files)[:150]
            nodes = [{"symbol_id": p, "qualified_name": p.split('/')[-1], "file": p,
                      "start_line": 1, "end_line": max(1, len(index.files[p].splitlines())), "kind": "file"} for p in paths]
            edges, seen = [], set()
            for edge in index.edges:
                a = index.graph.symbols[edge.source_symbol_id].file_path
                b = index.graph.symbols[edge.target_symbol_id].file_path
                if a != b and a in paths and b in paths and (a, b) not in seen:
                    edges.append({**edge.to_dict(), "source": a, "target": b})
                    seen.add((a, b))
            return {"nodes": nodes, "edges": edges, "paths": [], "version_key": index.manifest["version_key"],
                    "unresolved": index.extra.get("unresolved", [])[:100],
                    "unresolved_count": len(index.extra.get("unresolved", [])),
                    "message": f"{len(paths)} of {len(index.files)} source files · select a file to explore its symbols",
                    "status": "SEARCH_LIMIT_REACHED" if len(index.files) > 150 else "OK"}
        symbols = [s for s in index.symbols if s.symbol_id in index.graph.graph and (not file or s.file_path == file)]
        ids = {s.symbol_id for s in symbols[:150]}
        return {**index.graph.subgraph(ids), "version_key": index.manifest["version_key"],
                "message": f"{len(ids)} of {len(symbols)} symbols · select a file to focus" if len(symbols) > 150 else f"{len(ids)} symbols in this snapshot",
                "status": "SEARCH_LIMIT_REACHED" if len(symbols) > 150 else "OK",
                "unresolved": index.extra.get("unresolved", [])[:100]}

    @app.get("/api/checkpoint")
    def checkpoint():
        index = service.get("working-tree")
        with app.state.change_lock:
            cached = app.state.change_check
            if cached["key"] != index.manifest["version_key"] or time.monotonic() - cached["at"] > 10:
                files, _, _ = read_snapshot(Path(index.manifest["repository_path"]), "working-tree", service.settings)
                cached.update(at=time.monotonic(), key=index.manifest["version_key"],
                              changed=snapshot_hash(files) != index.manifest["source_hash"])
            return {"changed": cached["changed"], "version_key": cached["key"]}

    @app.post("/api/compare")
    def compare(body: CompareRequest):
        return compare_indexes(service.get(body.version_a), service.get(body.version_b), body.query, body.version_a, body.version_b)

    @app.get("/api/symbol/{symbol_id:path}")
    def symbol(symbol_id: str, version: str = "working-tree"):
        index = service.get(version)
        if symbol_id not in index.graph.symbols:
            raise HTTPException(404, "Unknown symbol")
        return {**asdict(index.graph.symbols[symbol_id]), "callers": index.graph.callers(symbol_id),
                "callees": index.graph.callees(symbol_id), "neighbors": index.graph.neighbors(symbol_id)}

    static = ROOT / "frontend" / "dist"
    if static.exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/")
        def frontend():
            return FileResponse(static / "index.html")
    return app


app = create_app()
