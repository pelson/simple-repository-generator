"""
Tests for MirroringRepository.
"""
from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import httpx
import pytest
from simple_repository import errors, model
from simple_repository.components.metadata_injector import MetadataInjectorRepository

from simple_repository_generator import MirroringRepository
from simple_repository_generator._flat import FlatDirectoryRepository


def _write_wheel(path: Path, dist_info: str, metadata: str) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{dist_info}/METADATA", metadata)
        zf.writestr(f"{dist_info}/WHEEL", "Wheel-Version: 1.0\n")


def _make_dist(root: Path) -> Path:
    dist = root / "dist"
    dist.mkdir()
    _write_wheel(
        dist / "foo_bar-1.0-py3-none-any.whl",
        "foo_bar-1.0.dist-info",
        "Metadata-Version: 2.1\nName: foo-bar\nVersion: 1.0\n",
    )
    return dist


def test_mirrors_files_and_rewrites_urls(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path)
    mirror = tmp_path / "mirror"

    async def _run() -> model.ProjectDetail:
        async with httpx.AsyncClient() as client:
            repo = MirroringRepository(
                FlatDirectoryRepository(dist), mirror, http_client=client,
            )
            page = await repo.get_project_page("foo-bar")
            resource = await repo.get_resource(
                "foo-bar", "foo_bar-1.0-py3-none-any.whl",
            )
            assert isinstance(resource, model.LocalResource)
            assert resource.path == mirror / "foo-bar" / "foo_bar-1.0-py3-none-any.whl"
            return page

    page = asyncio.run(_run())

    wheel = mirror / "foo-bar" / "foo_bar-1.0-py3-none-any.whl"
    assert wheel.is_file()
    (file,) = page.files
    assert file.url == str(wheel)


def test_mirrors_metadata_sidecar_when_advertised(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path)
    mirror = tmp_path / "mirror"

    async def _run() -> model.ProjectDetail:
        async with httpx.AsyncClient() as client:
            source = MetadataInjectorRepository(
                FlatDirectoryRepository(dist), client,
            )
            repo = MirroringRepository(source, mirror, http_client=client)
            return await repo.get_project_page("foo-bar")

    page = asyncio.run(_run())

    sidecar = mirror / "foo-bar" / "foo_bar-1.0-py3-none-any.whl.metadata"
    assert sidecar.is_file()
    assert "Name: foo-bar" in sidecar.read_text()
    (file,) = page.files
    assert file.dist_info_metadata


def test_raises_when_advertised_sidecar_unavailable(tmp_path: Path) -> None:
    """PEP 658 says the sidecar MUST be present when advertised. If the
    source advertises but cannot deliver, that's a source bug and the
    mirror must surface it rather than paper over it."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "foo_bar-1.0-py3-none-any.whl").write_bytes(b"not-a-real-wheel")
    mirror = tmp_path / "mirror"

    async def _run() -> None:
        async with httpx.AsyncClient() as client:
            source = MetadataInjectorRepository(
                FlatDirectoryRepository(dist), client,
            )
            repo = MirroringRepository(source, mirror, http_client=client)
            with pytest.raises(errors.ResourceUnavailable):
                await repo.get_project_page("foo-bar")

    asyncio.run(_run())
