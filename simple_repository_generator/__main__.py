"""
Command-line entry point for simple-repository-generator.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import httpx

from simple_repository import SimpleRepository
from simple_repository.components.http import HttpRepository
from simple_repository.components.metadata_injector import MetadataInjectorRepository
from simple_repository.components.priority_selected import (
    PrioritySelectedProjectsRepository,
)

from ._api import _dump_static_async
from ._flat import FlatDirectoryRepository
from ._mirroring import MirroringRepository
from ._writer import human_bytes


def _prepare_output(out_dir: Path, force: bool) -> None:
    if not out_dir.exists():
        return
    if not out_dir.is_dir():
        raise SystemExit(f"Output path exists and is not a directory: {out_dir}")
    if any(out_dir.iterdir()) and not force:
        raise SystemExit(
            f"Output directory {out_dir} is not empty. Pass --force to overwrite.",
        )


def _build_source(
    spec: str,
    http_client: httpx.AsyncClient,
) -> SimpleRepository:
    if spec.startswith(("http://", "https://")):
        return HttpRepository(url=spec, http_client=http_client)
    path = Path(spec)
    if not path.is_dir():
        raise SystemExit(f"Not a directory: {spec!r}")
    repo = FlatDirectoryRepository(path)
    if repo.file_count() == 0:
        raise SystemExit(
            f"No wheels or sdists found under {path}. "
            "Expected files named like <name>-<version>-*.whl or "
            "<name>-<version>.tar.gz.",
        )
    return repo


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="simple-repository-generator",
        description=(
            "Emit a static PEP 503 HTML index from local wheel/sdist "
            "directories or HTTP simple indexes."
        ),
    )
    parser.add_argument(
        "sources",
        metavar="SOURCE",
        nargs="+",
        help=(
            "Local directory (crawled recursively for wheels and sdists) "
            "or HTTP simple-index URL."
        ),
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

    async def _run() -> object:
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(httpx.AsyncClient())
            repos = [_build_source(spec, client) for spec in args.sources]
            repo: SimpleRepository = (
                repos[0]
                if len(repos) == 1
                else PrioritySelectedProjectsRepository(repos)
            )
            if args.copy:
                repo = MetadataInjectorRepository(repo, client)
                repo = MirroringRepository(
                    repo, args.output / "packages", http_client=client,
                )
            return await _dump_static_async(repo, args.output)

    result = asyncio.run(_run())

    print(f"Wrote simple index to {result.out_dir}")
    print(f"  sources:      {', '.join(args.sources)}")
    print(f"  projects:     {result.project_count}")
    print(f"  files:        {result.file_count}")
    repo_size = human_bytes(result.referenced_bytes)
    if result.repo_bytes != result.referenced_bytes:
        repo_size += f" ({human_bytes(result.repo_bytes)} in output directory)"
    print(f"  repo size:    {repo_size}")
    if not args.copy:
        print("  (hrefs point at the source files; use --copy for a portable tree)")


if __name__ == "__main__":
    main(sys.argv[1:])
