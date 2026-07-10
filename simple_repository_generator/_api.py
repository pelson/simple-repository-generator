"""
Public API for the static index generator.
"""
from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

from simple_repository import SimpleRepository, content_negotiation, model, serializer

from . import _writer


@dataclasses.dataclass(frozen=True)
class DumpResult:
    out_dir: Path
    project_count: int
    file_count: int
    copied_bytes: int  # 0 when copy_resources is False


async def _dump_static_async(
    repo: SimpleRepository,
    out_dir: Path,
    *,
    copy_resources: bool,
) -> DumpResult:
    fmt = content_negotiation.Format.HTML_V1
    out_dir.mkdir(parents=True, exist_ok=True)

    project_list = await repo.get_project_list()
    _writer.write_text(
        out_dir / "index.html",
        serializer.serialize(project_list, fmt),
    )

    file_count = 0
    copied_bytes = 0

    for project in project_list.projects:
        normalized = _writer.normalize(project.name)
        page = await repo.get_project_page(normalized)
        page_path = out_dir / "simple" / normalized / "index.html"

        if copy_resources:
            resource_paths: dict[str, Path] = {}
            for file in page.files:
                resource = await repo.get_resource(normalized, file.filename)
                dest = out_dir / "packages" / normalized / file.filename
                if isinstance(resource, model.LocalResource):
                    _writer.copy_local_resource(resource, dest)
                else:
                    raise TypeError(
                        f"Cannot copy resource of type {type(resource).__name__}; "
                        "only LocalResource is supported in v1.",
                    )
                copied_bytes += dest.stat().st_size
                resource_paths[file.filename] = dest
            page = _writer.rewrite_urls_relative(page, page_path, resource_paths)

        file_count += len(page.files)
        _writer.write_text(page_path, serializer.serialize(page, fmt))

    return DumpResult(
        out_dir=out_dir,
        project_count=len(project_list.projects),
        file_count=file_count,
        copied_bytes=copied_bytes,
    )


def dump_static(
    repo: SimpleRepository,
    out_dir: Path,
    *,
    copy_resources: bool = False,
) -> DumpResult:
    """Serialize *repo* as a static PEP 503 HTML tree under *out_dir*.

    When ``copy_resources`` is True, distribution files are copied into
    ``out_dir/packages/<normalized-name>/`` and the emitted pages use
    relative hrefs. When False, hrefs are passed through unchanged.
    """
    return asyncio.run(
        _dump_static_async(repo, out_dir, copy_resources=copy_resources),
    )
