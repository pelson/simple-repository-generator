"""
Filesystem writing helpers for the static index generator.
"""
from __future__ import annotations

import dataclasses
import os.path
import shutil
from pathlib import Path

import packaging.utils

from simple_repository import model


def normalize(name: str) -> str:
    return packaging.utils.canonicalize_name(name)


def rewrite_urls_relative(
    page: model.ProjectDetail,
    page_path: Path,
    resource_paths: dict[str, Path],
) -> model.ProjectDetail:
    """Return a copy of *page* whose file URLs are ``page_path``-relative paths
    into *resource_paths* (keyed by ``file.filename``)."""
    page_dir = page_path.parent
    new_files = tuple(
        dataclasses.replace(
            f,
            url=os.path.relpath(resource_paths[f.filename], start=page_dir),
        )
        for f in page.files
    )
    return dataclasses.replace(page, files=new_files)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_local_resource(resource: model.LocalResource, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resource.path, dest)
