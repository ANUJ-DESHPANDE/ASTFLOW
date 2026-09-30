"""Verify tracked release evidence without depending on checkout line endings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = "benchmark/results/P004-product-hardening"
MANIFEST = f"{ARTIFACTS}/artifact_hashes.json"
WINDOWS_HOME = re.compile(r"(?i)(?:file:/+)?[A-Z]:(\\{1,2}|/+)Users\1[A-Za-z0-9._-]+")
UNIX_HOME = re.compile(r"(?<![A-Za-z0-9:])/(?:home|Users)/[A-Za-z0-9._-]+")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def tracked_paths() -> list[str]:
    return [entry.decode("utf-8") for entry in git("ls-files", "-z").split(b"\0") if entry]


def check_personal_paths() -> bool:
    affected: list[str] = []
    for rel in tracked_paths():
        try:
            data = (ROOT / rel).read_bytes()
            text = data.decode("utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        if b"\0" in data:
            continue
        if WINDOWS_HOME.search(text) or UNIX_HOME.search(text):
            affected.append(rel)
    for rel in affected:
        print(f"Personal home path: {rel}")
    print(f"Tracked files with personal home paths: {len(affected)}")
    return not affected


def check_hashes(revision: str) -> bool:
    spec = lambda path: f":{path}" if revision == "index" else f"HEAD:{path}"
    manifest = json.loads(git("show", spec(MANIFEST)))
    tracked = {
        rel.removeprefix(f"{ARTIFACTS}/")
        for rel in tracked_paths()
        if rel.startswith(f"{ARTIFACTS}/") and rel != MANIFEST
    }
    if set(manifest) != tracked:
        print(f"Manifest membership mismatch: missing={sorted(tracked - set(manifest))}, extra={sorted(set(manifest) - tracked)}")
        return False
    failed: list[str] = []
    for rel, expected in sorted(manifest.items()):
        full_path = f"{ARTIFACTS}/{rel}"
        actual = hashlib.sha256(git("show", spec(full_path))).hexdigest()
        if actual != expected:
            failed.append(rel)
        if revision == "HEAD" and subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", full_path], cwd=ROOT, check=False
        ).returncode != 0:
            failed.append(f"{rel} (uncommitted change)")
    for rel in failed:
        print(f"Artifact mismatch: {rel}")
    print(f"P004 Git-blob hashes verified: {len(manifest) - len(failed)}/{len(manifest)}")
    print(f"Manifest excluded from self-hashing: {MANIFEST}")
    return not failed


def main() -> int:
    revision = "index" if "--staged" in sys.argv[1:] else "HEAD"
    return 0 if check_personal_paths() and check_hashes(revision) else 1


if __name__ == "__main__":
    raise SystemExit(main())
