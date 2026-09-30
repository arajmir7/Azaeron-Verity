"""Build an offline source snapshot. This command never fetches remote content."""

import argparse
import json
from pathlib import Path

from app.modules.similarity.public_index import build_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report.write_text(
        json.dumps(build_index(args.bundle, args.output), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
