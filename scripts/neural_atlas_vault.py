#!/usr/bin/env python3
"""Generate the Neural Atlas vault from the packaged Graphify inventory.

Reads the embedded `<script id="initial-data">` JSON from the VAYU workspace
page (read-only) and writes one markdown file per graph node with wiki links
for every graph edge. The Brain Map builder then renders this vault instead of
the sample notes, so the Neural Atlas shows the real VAOS/Vyndios business
graph.
"""
import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import spark_neural_atlas as atlas  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".",
                        help="SPARK checkout root containing vendor/vayu-workspace")
    parser.add_argument("--out", required=True,
                        help="directory that receives the generated atlas vault")
    args = parser.parse_args()
    try:
        result = atlas.build_vault(args.root, args.out)
    except atlas.AtlasDataError as error:
        print(f"neural-atlas: {error}", file=sys.stderr)
        return 1
    print(f"neural-atlas: {result['nodes']} nodes, {result['links']} graph links "
          f"written as {result['files']} markdown files -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
