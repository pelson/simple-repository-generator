"""
A repository component that mirrors a source repository's resources onto
disk, and rewrites `File.url` to point at the on-disk copy.
"""
from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import httpx
import packaging.utils

from simple_repository import SimpleRepository, model
from simple_repository.components import core

from . import _writer


class MirroringRepository(core.RepositoryContainer):
    """Wraps a source repository and, on ``get_project_page``, streams every
    referenced resource into ``mirror_dir`` and rewrites ``file.url`` to a
    string pointing at the on-disk copy.

    For every file whose ``dist_info_metadata`` is set, the ``.metadata``
    sibling is fetched from the source and written next to the file; this
    is required by PEP 658 / PEP 714 for a compliant mirror. If the source
    cannot produce the sidecar, the underlying ``ResourceUnavailable``
    propagates.
    """

    def __init__(
        self,
        source: SimpleRepository,
        mirror_dir: Path,
        *,
        http_client: httpx.AsyncClient,
    ) -> None:
        super().__init__(source)
        # Absolute so hosted-vs-external accounting downstream can compare
        # paths without caring about the caller's cwd.
        self._mirror_dir = mirror_dir.resolve()
        self._http_client = http_client
        self._mirror_paths: dict[tuple[str, str], Path] = {}

    async def get_project_page(
        self,
        project_name: str,
        *,
        request_context: typing.Optional[model.RequestContext] = None,
    ) -> model.ProjectDetail:
        page = await self.source.get_project_page(
            project_name,
            request_context=request_context,
        )
        normalized = packaging.utils.canonicalize_name(page.name)

        new_files: list[model.File] = []
        for file in page.files:
            dest = self._mirror_dir / normalized / file.filename
            await self._copy_if_needed(page.name, file.filename, dest)

            if file.dist_info_metadata:
                meta = await self.source.get_resource(
                    page.name, file.filename + ".metadata",
                )
                await _writer.write_resource(
                    meta,
                    dest.with_name(dest.name + ".metadata"),
                    self._http_client,
                )

            self._mirror_paths[(normalized, file.filename)] = dest
            new_files.append(dataclasses.replace(file, url=str(dest)))

        return dataclasses.replace(page, files=tuple(new_files))

    async def get_resource(
        self,
        project_name: str,
        resource_name: str,
        *,
        request_context: typing.Optional[model.RequestContext] = None,
    ) -> model.Resource:
        normalized = packaging.utils.canonicalize_name(project_name)
        cached = self._mirror_paths.get((normalized, resource_name))
        if cached is not None:
            return model.LocalResource(path=cached)
        return await self.source.get_resource(
            project_name,
            resource_name,
            request_context=request_context,
        )

    async def _copy_if_needed(
        self,
        project_name: str,
        filename: str,
        dest: Path,
    ) -> None:
        resource = await self.source.get_resource(project_name, filename)
        if dest.exists() and isinstance(resource, model.LocalResource):
            try:
                if dest.stat().st_size == resource.path.stat().st_size:
                    return
            except OSError:
                pass
        await _writer.write_resource(resource, dest, self._http_client)
