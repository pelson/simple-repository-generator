"""
Public API for the static index generator.
"""
from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import httpx

from simple_repository import (
    SimpleRepository,
    content_negotiation,
    errors,
    model,
    serializer,
)

from . import _writer


@dataclasses.dataclass(frozen=True)
class DumpResult:
    out_dir: Path
    project_count: int
    file_count: int
    #: Total on-disk size of the emitted tree (index + any copied resources).
    repo_bytes: int
    #: Sum of file.size across every distribution the index references.
    #: For --copy this equals the copied bytes; without --copy it is the size
    #: of the upstream files (as reported by the source repository).
    referenced_bytes: int


async def _dump_static_async(
    repo: SimpleRepository,
    out_dir: Path,
    *,
    copy_resources: bool,
    http_client: httpx.AsyncClient,
) -> DumpResult:
    fmt = content_negotiation.Format.HTML_V1
    out_dir.mkdir(parents=True, exist_ok=True)

    project_list = await repo.get_project_list()
    _writer.write_text(
        out_dir / "simple" / "index.html",
        serializer.serialize(project_list, fmt),
    )

    file_count = 0
    referenced_bytes = 0

    for project in project_list.projects:
        normalized = _writer.normalize(project.name)
        page = await repo.get_project_page(normalized)
        page_path = out_dir / "simple" / normalized / "index.html"

        if copy_resources:
            resource_paths: dict[str, Path] = {}
            for file in page.files:
                resource = await repo.get_resource(normalized, file.filename)
                dest = out_dir / "packages" / normalized / file.filename
                await _writer.write_resource(resource, dest, http_client)
                resource_paths[file.filename] = dest

                # Try to materialize the sibling .metadata file (PEP 658).
                # Best-effort: if the injector can't extract METADATA
                # (invalid wheel etc.), skip it.
                if file.dist_info_metadata and file.filename.endswith(".whl"):
                    try:
                        meta = await repo.get_resource(
                            normalized, file.filename + ".metadata",
                        )
                    except errors.ResourceUnavailable:
                        pass
                    else:
                        await _writer.write_resource(
                            meta,
                            dest.with_name(dest.name + ".metadata"),
                            http_client,
                        )
            page = _writer.rewrite_urls_relative(page, page_path, resource_paths)

        for file in page.files:
            file_count += 1
            if file.size is not None:
                referenced_bytes += file.size

        _writer.write_text(page_path, serializer.serialize(page, fmt))

    return DumpResult(
        out_dir=out_dir,
        project_count=len(project_list.projects),
        file_count=file_count,
        repo_bytes=_writer.dir_size(out_dir),
        referenced_bytes=referenced_bytes,
    )


async def _dump_static_with_client(
    repo: SimpleRepository,
    out_dir: Path,
    *,
    copy_resources: bool,
) -> DumpResult:
    async with httpx.AsyncClient() as client:
        return await _dump_static_async(
            repo, out_dir, copy_resources=copy_resources, http_client=client,
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
        _dump_static_with_client(repo, out_dir, copy_resources=copy_resources),
    )
