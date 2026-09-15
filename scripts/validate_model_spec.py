from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_spec_lib import load_spec, validate_spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical model-spec.json references and readiness.")
    parser.add_argument("spec", help="Path to model-spec.json.")
    parser.add_argument(
        "--require-approved",
        action="store_true",
        help="Require meta.review_status to be approved.",
    )
    parser.add_argument(
        "--require-reviewed",
        action="store_true",
        help="Require meta.review_status to be reviewed or approved.",
    )
    args = parser.parse_args()

    path = Path(args.spec)
    if not path.exists():
        print(f"{path}: file not found", file=sys.stderr)
        return 1

    try:
        spec = load_spec(path)
        errors = validate_spec(
            spec,
            require_approved=args.require_approved,
            require_reviewed=args.require_reviewed,
        )
    except (ValueError, OSError) as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"OK {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
