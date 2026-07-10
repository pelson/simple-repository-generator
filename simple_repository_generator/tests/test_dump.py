"""
Tests for dump_static and the CLI.
"""
from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import httpx
import pytest
from simple_repository.components.local import LocalRepository

from simple_repository_generator import MirroringRepository, dump_static
from simple_repository_generator._api import _dump_static_async
from simple_repository_generator.__main__ import main as cli_main


def _write_wheel(path: Path, dist_info: str, metadata: str) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{dist_info}/METADATA", metadata)
        zf.writestr(f"{dist_info}/WHEEL", "Wheel-Version: 1.0\n")


def _make_flat_dist(root: Path) -> Path:
    """A flat ``dist/`` directory of wheels/sdists (no per-project subdirs)."""
    dist = root / "dist"
    dist.mkdir()
    _write_wheel(
        dist / "foo_bar-1.0-py3-none-any.whl",
        "foo_bar-1.0.dist-info",
        "Metadata-Version: 2.1\nName: foo-bar\nVersion: 1.0\n",
    )
    (dist / "foo_bar-1.0.tar.gz").write_bytes(b"sdist-bytes")
    _write_wheel(
        dist / "baz-0.1-py3-none-any.whl",
        "baz-0.1.dist-info",
        "Metadata-Version: 2.1\nName: baz\nVersion: 0.1\n",
    )
    (dist / "README.txt").write_text("not a distribution")
    return dist


def _make_local_layout(root: Path) -> Path:
    index = root / "index"
    (index / "foo-bar").mkdir(parents=True)
    _write_wheel(
        index / "foo-bar" / "foo_bar-1.0-py3-none-any.whl",
        "foo_bar-1.0.dist-info",
        "Metadata-Version: 2.1\nName: foo-bar\nVersion: 1.0\n",
    )
    (index / "baz").mkdir(parents=True)
    _write_wheel(
        index / "baz" / "baz-0.1-py3-none-any.whl",
        "baz-0.1.dist-info",
        "Metadata-Version: 2.1\nName: baz\nVersion: 0.1\n",
    )
    return index


def test_dump_without_copy(tmp_path: Path) -> None:
    index = _make_local_layout(tmp_path)
    out = tmp_path / "out"

    foo_wheel = index / "foo-bar" / "foo_bar-1.0-py3-none-any.whl"
    baz_wheel = index / "baz" / "baz-0.1-py3-none-any.whl"
    expected_bytes = foo_wheel.stat().st_size + baz_wheel.stat().st_size

    result = dump_static(LocalRepository(index), out)

    assert result.project_count == 2
    assert result.file_count == 2
    assert result.referenced_bytes == expected_bytes

    assert (out / "simple" / "index.html").is_file()
    assert (out / "simple" / "foo-bar" / "index.html").is_file()
    assert (out / "simple" / "baz" / "index.html").is_file()
    assert not (out / "packages").exists()

    page = (out / "simple" / "foo-bar" / "index.html").read_text()
    assert f'href="file://{index}/foo-bar/foo_bar-1.0-py3-none-any.whl' in page


def test_dump_with_copy(tmp_path: Path) -> None:
    index = _make_local_layout(tmp_path)
    out = tmp_path / "out"

    foo_wheel = index / "foo-bar" / "foo_bar-1.0-py3-none-any.whl"
    baz_wheel = index / "baz" / "baz-0.1-py3-none-any.whl"
    expected_bytes = foo_wheel.stat().st_size + baz_wheel.stat().st_size
    original_wheel_bytes = foo_wheel.read_bytes()

    async def _run() -> object:
        async with httpx.AsyncClient() as client:
            repo = MirroringRepository(
                LocalRepository(index), out / "packages", http_client=client,
            )
            return await _dump_static_async(repo, out)

    result = asyncio.run(_run())

    assert result.project_count == 2
    assert result.file_count == 2
    assert result.referenced_bytes == expected_bytes
    assert result.repo_bytes > result.referenced_bytes

    wheel = out / "packages" / "foo-bar" / "foo_bar-1.0-py3-none-any.whl"
    assert wheel.read_bytes() == original_wheel_bytes

    page = (out / "simple" / "foo-bar" / "index.html").read_text()
    assert 'href="../../packages/foo-bar/foo_bar-1.0-py3-none-any.whl' in page
    assert "file://" not in page


def test_cli_crawls_flat_directory(tmp_path: Path) -> None:
    dist = _make_flat_dist(tmp_path)
    out = tmp_path / "out"

    cli_main(["--output", str(out), "--copy", str(dist)])

    # Two normalized projects should have been inferred from filenames.
    assert (out / "simple" / "foo-bar" / "index.html").is_file()
    assert (out / "simple" / "baz" / "index.html").is_file()
    assert (out / "packages" / "foo-bar" / "foo_bar-1.0-py3-none-any.whl").is_file()
    assert (out / "packages" / "foo-bar" / "foo_bar-1.0.tar.gz").is_file()
    assert (out / "packages" / "baz" / "baz-0.1-py3-none-any.whl").is_file()

    # The stray README.txt must not appear anywhere.
    assert not (out / "packages" / "readme").exists()


def test_cli_advertises_metadata_only_with_copy(tmp_path: Path) -> None:
    dist = _make_flat_dist(tmp_path)

    # Without --copy we do not host the .metadata sidecars, so we must not
    # advertise data-core-metadata (that would be a broken promise to pip).
    out_nocopy = tmp_path / "out-nocopy"
    cli_main(["--output", str(out_nocopy), str(dist)])
    nocopy_page = (out_nocopy / "simple" / "foo-bar" / "index.html").read_text()
    # We check for the attribute form: the bare substring
    # "data-core-metadata" also appears inside the progressive-enhancement
    # <script> as a CSS selector, but no <a> should carry the attribute.
    assert 'data-core-metadata="' not in nocopy_page

    # With --copy, MetadataInjectorRepository is enabled and pages advertise
    # the sidecar (which we also materialise on disk in the copy branch,
    # exercised in test_cli_crawls_flat_directory).
    out_copy = tmp_path / "out-copy"
    cli_main(["--output", str(out_copy), "--copy", str(dist)])
    copy_page = (out_copy / "simple" / "foo-bar" / "index.html").read_text()
    assert 'data-core-metadata="true"' in copy_page


def test_cli_refuses_missing_source(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Not a directory"):
        cli_main(["--output", str(tmp_path / "out"), str(tmp_path / "does-not-exist")])


def test_cli_refuses_empty_source(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit, match="No wheels or sdists"):
        cli_main(["--output", str(tmp_path / "out"), str(empty)])


def test_cli_refuses_nonempty_output_without_force(tmp_path: Path) -> None:
    dist = _make_flat_dist(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "leftover").write_text("x")

    with pytest.raises(SystemExit, match="not empty"):
        cli_main(["--output", str(out), str(dist)])


def test_cli_prints_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    dist = _make_flat_dist(tmp_path)
    out = tmp_path / "out"

    cli_main(["--output", str(out), "--copy", str(dist)])

    captured = capsys.readouterr().out
    assert "projects:     2" in captured
    assert "files:        3" in captured
    assert "repo size:" in captured
    assert "referenced:" in captured
