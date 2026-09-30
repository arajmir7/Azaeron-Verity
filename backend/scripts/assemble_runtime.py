"""Assemble CPython and its required native libraries onto a matching distroless OS.

Run only in the Docker builder. Preserve package provenance for every added system
library; scanners must see the actual final runtime rather than a stripped SBOM.
"""

import json
import argparse
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path("/runtime-root")
BASE = Path("/base")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--include-sqlite",
    action="store_true",
    help="Keep CPython SQLite support for the isolated unit-test image",
)
args = parser.parse_args()
local = ROOT / "usr/local"
shutil.copytree("/usr/local", local, symlinks=True)
# Interactive/database tools are not application dependencies. Verification keeps
# the full CPython distribution, including SQLite, in its separate build target.
for pattern in (
    "bin/pip*",
    "bin/2to3*",
    "bin/idle*",
    "bin/pydoc*",
    "include",
    "lib/pkgconfig",
    "lib/python3.12/ensurepip",
    "lib/python3.12/test",
    "lib/python3.12/idlelib",
    "lib/python3.12/tkinter",
    "lib/python3.12/site-packages/pip*",
    "lib/python3.12/lib-dynload/_curses*",
    "lib/python3.12/lib-dynload/readline*",
    "lib/python3.12/lib-dynload/_dbm*",
    "lib/python3.12/lib-dynload/_gdbm*",
    "lib/python3.12/lib-dynload/_uuid*",
    "lib/python3.12/lib-dynload/_tkinter*",
):
    for target in local.glob(pattern):
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
if not args.include_sqlite:
    for target in local.glob("lib/python3.12/lib-dynload/_sqlite3*"):
        target.unlink()
packages = set()
libraries = {}
for target in sorted(local.rglob("*")):
    if not target.is_file() or target.is_symlink():
        continue
    with target.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            continue
    original = Path("/") / target.relative_to(ROOT)
    result = subprocess.run(["ldd", str(original)], capture_output=True, text=True)
    if "not found" in result.stdout:
        raise RuntimeError(f"Unresolved native dependency: {original}")
    for raw in re.findall(r"(?:=>\s*)?(/[^\s]+)", result.stdout):
        source = Path(raw)
        if str(source).startswith("/usr/local/"):
            continue
        # Keep distroless-owned libc/OpenSSL and their package records intact.
        if (BASE / source.relative_to("/")).exists():
            continue
        resolved = source.resolve()
        # Debian 13 uses merged-/usr symlinks. Copy into the canonical directory
        # rather than replacing the base image's /lib -> usr/lib symlink.
        # Preserve the SONAME (e.g. libstdc++.so.6), not only its versioned target.
        destination = source.parent.resolve() / source.name
        dest = ROOT / destination.relative_to("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, dest)
        owner = subprocess.check_output(
            ["dpkg-query", "-S", str(resolved)], text=True
        ).split(": ", 1)[0]
        packages.add(owner)
        libraries[str(source)] = owner
status = ROOT / "var/lib/dpkg/status.d"
status.mkdir(parents=True, exist_ok=True)
for package in sorted(packages):
    record = subprocess.check_output(["dpkg-query", "-s", package], text=True)
    (status / ("cpython-" + package.replace(":", "-"))).write_text(record)
metadata = ROOT / "usr/share/azaeron"
metadata.mkdir(parents=True, exist_ok=True)
(metadata / "native-libraries.json").write_text(json.dumps(libraries, indent=2) + "\n")
