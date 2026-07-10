"""
Filesystem writing helpers for the static index generator.
"""
from __future__ import annotations

import dataclasses
import os.path
import shutil
from pathlib import Path

import httpx
import packaging.utils

from simple_repository import model


def normalize(name: str) -> str:
    return packaging.utils.canonicalize_name(name)


def rewrite_urls_relative(
    page: model.ProjectDetail,
    page_path: Path,
) -> model.ProjectDetail:
    """Return a copy of *page* in which any file URL that is an absolute
    filesystem path is rewritten to be relative to ``page_path``. Files
    whose URL uses a URL scheme (``file://``, ``https://``, ...) are left
    unchanged."""
    page_dir = page_path.parent
    new_files = tuple(
        dataclasses.replace(f, url=os.path.relpath(f.url, start=page_dir))
        if os.path.isabs(f.url)
        else f
        for f in page.files
    )
    return dataclasses.replace(page, files=new_files)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def write_resource(
    resource: model.Resource,
    dest: Path,
    http_client: httpx.AsyncClient,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(resource, model.LocalResource):
        shutil.copyfile(resource.path, dest)
    elif isinstance(resource, model.TextResource):
        dest.write_text(resource.text, encoding="utf-8")
    elif isinstance(resource, model.HttpResource):
        async with http_client.stream("GET", resource.url) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    fh.write(chunk)
    else:
        raise TypeError(f"Unsupported resource type: {type(resource).__name__}")


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PiB"
