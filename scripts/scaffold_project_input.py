from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def scaffold(output_dir: Path, overwrite: bool) -> list[Path]:
    skill_dir = Path(__file__).resolve().parents[1]
    template_dir = skill_dir / "assets" / "templates" / "project-input"
    if not template_dir.exists():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    for template in sorted(template_dir.glob("*.template.md")):
        target = output_dir / template.name.replace(".template", "")
        if target.exists() and not overwrite:
            continue
        shutil.copyfile(template, target)
        created.append(target)

    return created


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create post-model docs/input/00-07 files from bundled project-input templates."
    )
    parser.add_argument(
        "--output",
        default="docs/input",
        help="Output directory for generated project input files. Default: docs/input",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )
    args = parser.parse_args()

    created = scaffold(Path(args.output), args.overwrite)
    for path in created:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
