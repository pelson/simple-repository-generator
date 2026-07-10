"""
A SimpleRepository over a flat directory of wheels and sdists.
Project name and version are inferred from filenames per PEP 427 / PEP 625.
"""
from __future__ import annotations

import os
import typing
from datetime import datetime
from pathlib import Path

from packaging.utils import (
    InvalidSdistFilename,
    InvalidWheelFilename,
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)

from simple_repository import errors, model
from simple_repository.components import core

_SDIST_SUFFIXES = (".tar.gz", ".zip")


def _infer_project(filename: str) -> str | None:
    if filename.endswith(".whl"):
        try:
            return canonicalize_name(parse_wheel_filename(filename)[0])
        except InvalidWheelFilename:
            return None
    for suffix in _SDIST_SUFFIXES:
        if filename.endswith(suffix):
            try:
                return canonicalize_name(parse_sdist_filename(filename)[0])
            except InvalidSdistFilename:
                return None
    return None


class FlatDirectoryRepository(core.SimpleRepository):
    """Index every wheel/sdist found under *root* (recursively) as a
    SimpleRepository. Files are grouped by the project name parsed from the
    filename."""

    def __init__(self, root: Path) -> None:
        if not root.is_dir():
            raise ValueError(f"Not a directory: {root}")
        self._root = root.absolute()
        self._index: dict[str, dict[str, Path]] = {}
        for path in sorted(self._root.rglob("*")):
            if not path.is_file():
                continue
            name = _infer_project(path.name)
            if name is None:
                continue
            self._index.setdefault(name, {})[path.name] = path

    def project_count(self) -> int:
        return len(self._index)

    def file_count(self) -> int:
        return sum(len(files) for files in self._index.values())

    async def get_project_list(
        self,
        *,
        request_context: typing.Optional[model.RequestContext] = None,
    ) -> model.ProjectList:
        return model.ProjectList(
            meta=model.Meta("1.0"),
            projects=frozenset(
                model.ProjectListElement(name) for name in self._index
            ),
        )

    async def get_project_page(
        self,
        project_name: str,
        *,
        request_context: typing.Optional[model.RequestContext] = None,
    ) -> model.ProjectDetail:
        normalized = canonicalize_name(project_name)
        entries = self._index.get(normalized)
        if entries is None:
            raise errors.PackageNotFoundError(project_name)

        files: list[model.File] = []
        for filename, path in sorted(entries.items()):
            stat = os.stat(path)
            files.append(
                model.File(
                    filename=filename,
                    url=path.as_uri(),
                    hashes={},
                    upload_time=datetime.fromtimestamp(stat.st_mtime),
                    size=stat.st_size,
                ),
            )
        return model.ProjectDetail(
            meta=model.Meta("1.1"),
            name=normalized,
            files=tuple(files),
        )

    async def get_resource(
        self,
        project_name: str,
        resource_name: str,
        *,
        request_context: typing.Optional[model.RequestContext] = None,
    ) -> model.Resource:
        normalized = canonicalize_name(project_name)
        entries = self._index.get(normalized)
        if entries is None:
            raise errors.PackageNotFoundError(project_name)
        path = entries.get(resource_name)
        if path is None:
            raise errors.ResourceUnavailable(resource_name)
        return model.LocalResource(path=path)
