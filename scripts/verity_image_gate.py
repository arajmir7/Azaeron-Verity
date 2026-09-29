"""Scan every distinct local image without exposing Docker's socket to the scanner."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

SCANNER = "aquasec/trivy@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="*")
    parser.add_argument(
        "--compose", type=Path, help="Scan every image in all Compose profiles"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("docs/verity/evidence/images")
    )
    args = parser.parse_args()
    if not args.images and args.compose is None:
        parser.error("provide images or --compose")
    args.output.mkdir(parents=True, exist_ok=True)
    images = list(args.images)
    inventory = {}
    if args.compose is not None:
        config = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "compose",
                    "--profile",
                    "*",
                    "-f",
                    str(args.compose),
                    "config",
                    "--format",
                    "json",
                ]
            )
        )
        for service, definition in config["services"].items():
            name = definition.get("image")
            if not name:
                parser.error(f"Compose service {service} has no resolved image")
            inventory[service] = name
            images.append(name)
        (args.output / "inventory.json").write_text(
            json.dumps(inventory, indent=2, sort_keys=True) + "\n"
        )
    images = list(dict.fromkeys(images))
    metadata_by_name = {
        name: json.loads(subprocess.check_output(["docker", "image", "inspect", name]))[
            0
        ]
        for name in images
    }
    by_image_id: dict[str, list[str]] = {}
    for name in images:
        by_image_id.setdefault(metadata_by_name[name]["Id"], []).append(name)
    results = []
    for index, aliases in enumerate(by_image_id.values()):
        name = aliases[0]
        metadata = metadata_by_name[name]
        with tempfile.TemporaryDirectory(prefix="verity-image-") as directory:
            # Docker writes the archive as the host runner, while the isolated
            # scanner reads it from inside a container. TemporaryDirectory's
            # default 0700 mode prevents traversal on Linux runners.
            os.chmod(directory, 0o755)
            archive = Path(directory) / "image.tar"
            subprocess.run(
                ["docker", "image", "save", name, "-o", str(archive)], check=True
            )
            os.chmod(archive, 0o644)
            base = [
                "docker",
                "run",
                "--rm",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "-v",
                f"{archive}:/scan/image.tar:ro",
                "-v",
                "verity-scanner-cache:/root/.cache/trivy",
                SCANNER,
                "image",
                "--input",
                "/scan/image.tar",
            ]
            for gate, options in [
                (
                    "vulnerabilities",
                    [
                        "--scanners",
                        "vuln",
                        "--severity",
                        "HIGH,CRITICAL",
                        "--exit-code",
                        "1",
                        "--format",
                        "json",
                    ],
                ),
                ("sbom", ["--format", "cyclonedx"]),
            ]:
                filename = f"image-{index}-{gate}"
                report = args.output / f"{filename}.json"
                with report.open("w") as output, (args.output / f"{filename}.log").open(
                    "w"
                ) as log:
                    code = subprocess.run(
                        base + options,
                        stdout=output,
                        stderr=log,
                    ).returncode
                try:
                    parsed = json.loads(report.read_text())
                    valid = (
                        isinstance(parsed.get("Results"), list)
                        if gate == "vulnerabilities"
                        else parsed.get("bomFormat") == "CycloneDX"
                    )
                except (json.JSONDecodeError, AttributeError):
                    valid = False
                if not valid:
                    status = "ERROR"
                elif code == 0:
                    status = "PASS"
                elif gate == "vulnerabilities" and code == 1:
                    status = "FAIL"
                else:
                    status = "ERROR"
                results.append(
                    {
                        "image": name,
                        "aliases": aliases,
                        "image_id": metadata["Id"],
                        "bytes": metadata["Size"],
                        "gate": gate,
                        "status": status,
                        "exit_code": code if code else (0 if valid else 2),
                        "report": f"{filename}.json",
                        "scanner": SCANNER,
                    }
                )
                print(f"{name}: {gate} → {results[-1]['status']}", flush=True)
                (args.output / "results.json").write_text(
                    json.dumps(results, indent=2) + "\n"
                )
    return int(any(result["exit_code"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
