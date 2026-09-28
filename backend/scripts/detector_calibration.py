"""Evaluate frozen private detector scores without importing or downloading a model."""

import argparse
import json
from pathlib import Path

from app.modules.detection.intelligence.evaluation import evaluate_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate_bundle(json.loads(args.input.read_text()))
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("EXPERIMENTAL: evaluation recorded; no production promotion was performed")


if __name__ == "__main__":
    main()
