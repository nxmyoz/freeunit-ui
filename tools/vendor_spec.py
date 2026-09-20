#!/usr/bin/env python
"""Vendor FreeUnit's OpenAPI specification into the package.

unitd does not serve its own specification, so a copy is bundled and will drift
from whatever server it is pointed at. That is why everything built on it is
advisory: see freeunit_ui/schema/__init__.py.

    python tools/vendor_spec.py 1.36.1

Converts to JSON so the package needs no YAML dependency at runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

SOURCE = "https://github.com/freeunitorg/freeunit/archive/refs/tags/{version}.tar.gz"
TARGET = Path(__file__).resolve().parent.parent / "src" / "freeunit_ui" / "schema"


def main() -> int:
    """Download a release, extract its spec, and write it as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="FreeUnit release, e.g. 1.36.1")
    args = parser.parse_args()

    try:
        import yaml
    except ImportError:
        print("This script needs PyYAML: pip install pyyaml", file=sys.stderr)
        return 1

    url = SOURCE.format(version=args.version)
    print(f"fetching {url}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "src.tar.gz"
        with urllib.request.urlopen(url) as response, archive.open("wb") as handle:  # noqa: S310
            handle.write(response.read())

        member = f"freeunit-{args.version}/docs/unit-openapi.yaml"
        with tarfile.open(archive) as tar:
            extracted = tar.extractfile(member)
            if extracted is None:
                print(f"{member} not found in the release", file=sys.stderr)
                return 1
            spec = yaml.safe_load(extracted.read())

    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "unit-openapi.json").write_text(
        json.dumps(spec, indent=1, sort_keys=True), encoding="utf-8"
    )
    (TARGET / "VERSION").write_text(f"{args.version}\n", encoding="utf-8")
    count = len(spec.get("components", {}).get("schemas", {}))
    print(f"vendored {count} schemas from FreeUnit {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
