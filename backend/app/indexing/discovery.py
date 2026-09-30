"""Read repository bytes, never execute repository code or follow symlinks."""
import hashlib
import os
import subprocess
from pathlib import Path, PurePosixPath

from backend.app.config import Settings

EXCLUDED = {"node_modules", "dist", "build", "coverage", "vendor", ".next", ".cache", ".git", ".astflow", ".venv", "venv", "__pycache__"}
EXTENSIONS = {".js", ".mjs", ".cjs", ".jsx"}


def useful(path: str) -> bool:
    p = PurePosixPath(path)
    return (not any(part in EXCLUDED for part in p.parts)
            and p.suffix in EXTENSIONS
            and not path.endswith((".min.js", ".bundle.js", ".map")))


def git(repo: Path, *args: str, binary: bool = False):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout if binary else result.stdout.decode("utf-8", "replace").strip()


def read_snapshot(repo: Path, version: str, settings: Settings) -> tuple[dict[str, str], str, list[str]]:
    repo = repo.resolve(strict=True)
    if not repo.is_dir():
        raise ValueError("Repository path must be a directory")
    files, warnings = {}, []
    total_bytes = 0
    resolved = "working-tree"
    if version == "working-tree":
        # Git's own exclude rules include nested .gitignore files and .git/info/exclude.
        # Keep tracked files even if an ignore rule was added after they were tracked.
        allowed = None
        try:
            if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() == repo:
                listing = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z", binary=True)
                allowed = set(listing.decode("utf-8", "surrogateescape").strip("\0").split("\0"))
        except (ValueError, OSError):
            pass  # non-Git directories remain supported
        cache = settings.cache.resolve()
        for current, dirs, names in os.walk(
                repo, followlinks=False,
                onerror=lambda exc: warnings.append(f"Skipped unreadable directory: {exc.filename} ({type(exc).__name__})")):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (Path(current) / d).is_symlink()
                             and not getattr(Path(current) / d, "is_junction", lambda: False)()
                             and not (Path(current) / d).resolve().is_relative_to(cache))
            for name in sorted(names):
                path = Path(current) / name
                relative = path.relative_to(repo).as_posix()
                if not useful(relative) or (allowed is not None and relative not in allowed):
                    continue
                try:
                    if (path.is_symlink() or path.resolve().is_relative_to(cache)
                            or not path.resolve().is_relative_to(repo)):
                        continue
                    if path.stat().st_size > settings.max_file_bytes:
                        warnings.append(f"Skipped large file: {relative}")
                        continue
                    with path.open("rb") as stream:
                        raw = stream.read(settings.max_file_bytes + 1)
                    if len(raw) > settings.max_file_bytes:
                        warnings.append(f"Skipped large file: {relative}")
                        continue
                    total_bytes += len(raw)
                    if total_bytes > settings.max_total_bytes:
                        raise ValueError("Repository exceeds total source byte limit")
                    files[relative] = raw.decode("utf-8")
                except UnicodeDecodeError:
                    warnings.append(f"Skipped non-UTF-8 file: {relative}")
                except OSError as exc:
                    warnings.append(f"Skipped unreadable file: {relative} ({type(exc).__name__})")
                if len(files) > settings.max_files:
                    raise ValueError(f"Repository exceeds {settings.max_files} JavaScript files")
    else:
        if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
            raise ValueError("Select the Git repository root to index a revision")
        if version.startswith("-") or len(version) > 200:
            raise ValueError("Invalid Git revision")
        resolved = git(repo, "rev-parse", "--verify", "--end-of-options", f"{version}^{{commit}}")
        tree = git(repo, "ls-tree", "-r", "-z", resolved, binary=True)
        entries = []
        for raw in tree.split(b"\0"):
            if not raw:
                continue
            header, raw_path = raw.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            path = raw_path.decode("utf-8", "replace")
            if kind == "blob" and mode in {"100644", "100755"} and useful(path):
                entries.append((path, oid))
        if len(entries) > settings.max_files:
            raise ValueError(f"Repository exceeds {settings.max_files} JavaScript files")
        # One cat-file process, independent of working tree and checkout state.
        if entries:
            sizes = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch-check=%(objectsize)"],
                                   input="".join(oid + "\n" for _, oid in entries).encode(),
                                   capture_output=True, timeout=60, check=True).stdout.splitlines()
            accepted = []
            for entry, size_raw in zip(entries, sizes, strict=True):
                size = int(size_raw)
                if size > settings.max_file_bytes:
                    warnings.append(f"Skipped large file: {entry[0]}")
                    continue
                total_bytes += size
                if total_bytes > settings.max_total_bytes:
                    raise ValueError("Repository exceeds total source byte limit")
                accepted.append(entry)
            entries = accepted
            result = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"],
                                    input="".join(oid + "\n" for _, oid in entries).encode(),
                                    capture_output=True, timeout=120, check=True)
            data, offset = result.stdout, 0
            for path, _ in entries:
                end = data.index(b"\n", offset)
                size = int(data[offset:end].split()[-1])
                raw = data[end + 1:end + 1 + size]
                offset = end + size + 2
                if size > settings.max_file_bytes:
                    warnings.append(f"Skipped large file: {path}")
                    continue
                try:
                    files[path] = raw.decode("utf-8")
                except UnicodeDecodeError:
                    warnings.append(f"Skipped non-UTF-8 file: {path}")
    return dict(sorted(files.items())), resolved, warnings


def snapshot_hash(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path, source in sorted(files.items()):
        digest.update(path.encode() + b"\0" + source.encode() + b"\0")
    return digest.hexdigest()


def list_versions(repo: Path) -> list[dict]:
    versions = [{"name": "working-tree", "commit": None, "label": "Working tree"}]
    try:
        if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo.resolve():
            return versions
        head = git(repo, "rev-parse", "HEAD")
        versions.append({"name": "HEAD", "commit": head, "label": "HEAD"})
        for tag in git(repo, "tag", "--list").splitlines():
            if tag:
                versions.append({"name": tag, "commit": git(repo, "rev-parse", f"refs/tags/{tag}"), "label": tag})
        for row in git(repo, "log", "-12", "--format=%H%x09%s").splitlines():
            commit, message = row.split("\t", 1)
            versions.append({"name": commit, "commit": commit, "label": f"{commit[:7]} · {message}"})
    except (ValueError, OSError):
        pass
    return versions
