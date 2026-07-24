#!/usr/bin/env python3
"""Install the digest-pinned micromamba oracle used by conda detection."""

import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path


ORACLE_VERSION = "2.8.1-0"
ORACLE_ASSET = "micromamba-osx-arm64"
ORACLE_SHA256 = "de71a646b73af92dd663e6ddc78993a6a4d47ea28b5d8908c3cc2b9c3077e528"
ORACLE_URL = (
    "https://github.com/mamba-org/micromamba-releases/releases/download/"
    f"{ORACLE_VERSION}/{ORACLE_ASSET}"
)
ORACLE_PATH = (Path.home() / ".cache" / "research-codebase-audit" / "oracles"
               / f"micromamba-{ORACLE_VERSION}")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_oracle(path=ORACLE_PATH, url=ORACLE_URL, expected=ORACLE_SHA256):
    path = Path(path)
    if path.is_file() and sha256(path) == expected:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".micromamba.", dir=path.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        urllib.request.urlretrieve(url, temp)
        actual = sha256(temp)
        if actual != expected:
            temp.unlink(missing_ok=True)
            raise RuntimeError(
                f"micromamba digest mismatch: expected {expected}, actual {actual}"
            )
        temp.chmod(0o755)
        os.replace(temp, path)
        return True
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def main():
    try:
        changed = install_oracle()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    action = "installed" if changed else "verified"
    print(f"{action} micromamba {ORACLE_VERSION} at {ORACLE_PATH}")
    print(f"sha256 {ORACLE_SHA256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
