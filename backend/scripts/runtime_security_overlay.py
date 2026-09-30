"""Copy fixed Debian packages and truthful provenance into a distroless overlay.

Executed in the builder after signed stable APT installation. No package metadata
is removed: the old same-named record is replaced alongside its actual files.
"""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

DESTINATION = Path("/security-overlay")
VERSION = "3.5.7-1~deb13u3"
PACKAGES = ("libssl3t64", "openssl-provider-legacy")


def main():
    records = {}
    status = DESTINATION / "var/lib/dpkg/status.d"
    status.mkdir(parents=True, exist_ok=False)
    for package in PACKAGES:
        identity = (
            subprocess.check_output(
                ["dpkg-query", "-W", "-f=${Version} ${Architecture}", package],
                text=True,
            )
            .strip()
            .split()
        )
        if identity[0] != VERSION:
            raise RuntimeError("Unexpected security package version")
        files = subprocess.check_output(
            ["dpkg-query", "-L", package], text=True
        ).splitlines()
        hashes = {}
        for name in files:
            source = Path(name)
            if not source.is_absolute() or ".." in source.parts:
                raise RuntimeError("Invalid package file path")
            target = DESTINATION / source.relative_to("/")
            if source.is_symlink():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(source.readlink())
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        record = subprocess.check_output(["dpkg-query", "-s", package], text=True)
        (status / package).write_text(record)
        binary_package = subprocess.check_output(
            ["dpkg-query", "-W", "-f=${binary:Package}", package], text=True
        ).strip()
        checksums = Path(f"/var/lib/dpkg/info/{binary_package}.md5sums")
        shutil.copy2(checksums, status / (package + ".md5sums"))
        records[package] = {
            "version": VERSION,
            "architecture": identity[1],
            "files": hashes,
        }
    metadata = DESTINATION / "usr/share/azaeron"
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "stable-security-overlay.json").write_text(
        json.dumps(
            {"advisory": "DSA-6531-1", "packages": records}, sort_keys=True, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
