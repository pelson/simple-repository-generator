"""
Command-line entry point for simple-repository-generator.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from simple_repository import SimpleRepository
from simple_repository.components.local import LocalRepository
from simple_repository.components.priority_selected import (
    PrioritySelectedProjectsRepository,
)

from ._api import dump_static


def _looks_like_url(spec: str) -> bool:
    return spec.startswith(("http://", "https://"))


def _build_repository(dirs: list[str]) -> SimpleRepository:
    repos: list[SimpleRepository] = []
    for spec in dirs:
        if _looks_like_url(spec):
            raise SystemExit(
                f"HTTP sources are not supported in v1: {spec!r}. "
                "Pass a local directory instead.",
            )
        path = Path(spec)
        if not path.is_dir():
            raise SystemExit(f"Not a directory: {spec!r}")
        repos.append(LocalRepository(path))
    if len(repos) == 1:
        return repos[0]
    return PrioritySelectedProjectsRepository(repos)


def _prepare_output(out_dir: Path, force: bool) -> None:
    if not out_dir.exists():
        return
    if not out_dir.is_dir():
        raise SystemExit(f"Output path exists and is not a directory: {out_dir}")
    if any(out_dir.iterdir()) and not force:
        raise SystemExit(
            f"Output directory {out_dir} is not empty. Pass --force to overwrite.",
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="simple-repository-generator",
        description="Emit a static PEP 503 HTML index from local wheel/sdist directories.",
    )
    parser.add_argument(
        "dirs",
        metavar="DIR",
        nargs="+",
        help="One or more local directories (LocalRepository layout).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("build/simple-repo"),
        help="Destination directory (default: ./build/simple-repo).",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy distribution files into the output tree and rewrite hrefs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into a non-empty output directory.",
    )
    args = parser.parse_args(argv)

    _prepare_output(args.output, args.force)
    repo = _build_repository(args.dirs)
    result = dump_static(repo, args.output, copy_resources=args.copy)

    print(f"Wrote simple index to {result.out_dir}")
    print(f"  sources:      {', '.join(args.dirs)}")
    print(f"  projects:     {result.project_count}")
    print(f"  distributions:{result.file_count:>4}")
    if args.copy:
        print(f"  copied bytes: {result.copied_bytes:,}")
    else:
        print("  copy mode:    off (hrefs point at input file locations)")


if __name__ == "__main__":
    main(sys.argv[1:])
