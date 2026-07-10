"""
Public API for the static index generator.
"""
from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

from simple_repository import SimpleRepository

from . import _html, _writer


@dataclasses.dataclass(frozen=True)
class DumpResult:
    out_dir: Path
    project_count: int
    file_count: int
    #: Total on-disk size of the emitted tree (index + any mirrored resources).
    repo_bytes: int
    #: Sum of file.size across every distribution the index references.
    referenced_bytes: int


async def _dump_static_async(
    repo: SimpleRepository,
    out_dir: Path,
) -> DumpResult:
    out_dir.mkdir(parents=True, exist_ok=True)

    project_list = await repo.get_project_list()
    _writer.write_text(
        out_dir / "simple" / "index.html",
        _html.render_project_list(project_list),
    )

    file_count = 0
    referenced_bytes = 0

    for project in project_list.projects:
        normalized = _writer.normalize(project.name)
        page = await repo.get_project_page(normalized)
        page_path = out_dir / "simple" / normalized / "index.html"
        page = _writer.rewrite_urls_relative(page, page_path)

        for file in page.files:
            file_count += 1
            if file.size is not None:
                referenced_bytes += file.size

        _writer.write_text(page_path, _html.render_project_page(page))

    return DumpResult(
        out_dir=out_dir,
        project_count=len(project_list.projects),
        file_count=file_count,
        repo_bytes=_writer.dir_size(out_dir),
        referenced_bytes=referenced_bytes,
    )


def dump_static(repo: SimpleRepository, out_dir: Path) -> DumpResult:
    """Serialize *repo* as a static PEP 503 HTML tree under *out_dir*.

    Distribution hrefs are taken verbatim from ``repo``'s pages, except
    that absolute filesystem paths (as produced by
    :class:`~simple_repository_generator.MirroringRepository`) are
    rewritten relative to each page. To produce a portable, self-contained
    tree, wrap the source repository in ``MirroringRepository`` first.
    """
    return asyncio.run(_dump_static_async(repo, out_dir))
