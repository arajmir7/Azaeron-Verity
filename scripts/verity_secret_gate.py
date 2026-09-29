"""Reject source secret findings unless their exact fingerprint has been reviewed."""

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = r"(^\.git/|\.verity-local|\.venv|node_modules|model_assets|__pycache__|\.next|\.mypy_cache|\.pytest_cache|\.ruff_cache|docs/verification|docs/verity/evidence|test-results|package-lock|tsbuildinfo|docs/verity/secret-review.json)"


def main() -> int:
    report = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                "-m",
                "detect_secrets",
                "scan",
                "--all-files",
                "--exclude-files",
                EXCLUDED,
            ],
            cwd=ROOT,
        )
    )
    reviewed = json.loads((ROOT / "docs/verity/secret-review.json").read_text())
    allowed = {
        (entry["file"], entry["type"], entry["hashed_secret"])
        for entry in reviewed["reviewed"]
    }
    unreviewed = []
    for filename, findings in report["results"].items():
        for finding in findings:
            if (filename, finding["type"], finding["hashed_secret"]) not in allowed:
                unreviewed.append(
                    {
                        "file": filename,
                        "line": finding["line_number"],
                        "type": finding["type"],
                    }
                )
    output = ROOT / "docs/verity/evidence/secret-gate.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "status": "FAIL" if unreviewed else "PASS",
                "unreviewed": unreviewed,
                "reviewed_fingerprints": len(allowed),
                "scan": report,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"Secret gate: {len(unreviewed)} unreviewed findings; {len(allowed)} exact reviewed fingerprints"
    )
    return int(bool(unreviewed))


if __name__ == "__main__":
    raise SystemExit(main())
