"""Create two real Git commits without checking out or executing the demo source."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "examples" / "demo-repo"

OLD_AUTH = '''import { validateCredentials } from "./credentials.js";

/** Create an authenticated session before persistence was extracted. */
export function createSession(identity) {
  return { username: identity.username, expiresAt: Date.now() + 3600000 };
}

export class AuthService {
  constructor() {
    this.savedSession = null;
  }

  login(credentials) {
    const identity = validateCredentials(credentials);
    const session = createSession(identity);
    this.savedSession = session;
    return session;
  }

  /** Restore the saved authenticated session after application restart. */
  restore() {
    if (!this.savedSession || this.savedSession.expiresAt <= Date.now()) return null;
    return this.savedSession;
  }
}
'''


def setup():
    if not list(REPO.rglob("*.js")):
        raise RuntimeError("Demo source files are missing; restore examples/demo-repo before setup")
    def git(*args, input=None, env=None):
        result = subprocess.run(["git", "-C", str(REPO), *args], input=input, capture_output=True,
                                env=env, check=True)
        return result.stdout.decode().strip()

    if (REPO / ".git").exists():
        tags = git("tag", "--list").splitlines()
        if {"v1", "v2"} <= set(tags):
            print("Demo Git history ready: v1 -> v2")
            return
        raise RuntimeError("Demo already has Git history without v1/v2 tags; preserve it and use another fixture directory")
    git("init", "--initial-branch=main")
    files = {p.relative_to(REPO).as_posix(): p.read_bytes() for p in sorted(REPO.rglob("*"))
             if p.is_file() and ".git" not in p.relative_to(REPO).parts}
    previous = {**files, "auth/AuthService.js": OLD_AUTH.encode()}
    previous.pop("session/SessionManager.js", None)
    previous.pop("tests/session.test.js", None)
    index_path = ROOT / ".astflow" / "demo-git-index"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_INDEX_FILE": str(index_path), "GIT_AUTHOR_NAME": "ASTFLOW Demo",
           "GIT_AUTHOR_EMAIL": "demo@astflow.local", "GIT_COMMITTER_NAME": "ASTFLOW Demo",
           "GIT_COMMITTER_EMAIL": "demo@astflow.local", "GIT_AUTHOR_DATE": "2026-01-10T10:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-01-10T10:00:00+00:00"}

    def tree(sources):
        git("read-tree", "--empty", env=env)
        for path, contents in sorted(sources.items()):
            oid = git("hash-object", "-w", "--stdin", input=contents)
            git("update-index", "--add", "--cacheinfo", "100644", oid, path, env=env)
        return git("write-tree", env=env)

    v1 = git("commit-tree", tree(previous), "-m", "Restore sessions in AuthService", env=env)
    env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = "2026-01-11T10:00:00+00:00"
    v2 = git("commit-tree", tree(files), "-p", v1, "-m", "Extract persistent session lifecycle into SessionManager", env=env)
    git("update-ref", "refs/heads/main", v2)
    git("tag", "v1", v1)
    git("tag", "v2", v2)
    git("read-tree", v2)
    print(json.dumps({"repository": str(REPO), "v1": v1, "v2": v2}, indent=2))


if __name__ == "__main__":
    setup()
