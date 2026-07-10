"""
Tests for dump_static and the CLI.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from simple_repository.components.local import LocalRepository

from simple_repository_generator import dump_static
from simple_repository_generator.__main__ import main as cli_main


def _make_flat_dist(root: Path) -> Path:
    """A flat ``dist/`` directory of wheels/sdists (no per-project subdirs)."""
    dist = root / "dist"
    dist.mkdir()
    (dist / "foo_bar-1.0-py3-none-any.whl").write_bytes(b"wheel-bytes")
    (dist / "foo_bar-1.0.tar.gz").write_bytes(b"sdist-bytes")
    (dist / "baz-0.1-py3-none-any.whl").write_bytes(b"baz-wheel")
    (dist / "README.txt").write_text("not a distribution")
    return dist


def _make_local_layout(root: Path) -> Path:
    index = root / "index"
    (index / "foo-bar").mkdir(parents=True)
    (index / "foo-bar" / "foo_bar-1.0-py3-none-any.whl").write_bytes(b"wheel-bytes")
    (index / "baz").mkdir(parents=True)
    (index / "baz" / "baz-0.1-py3-none-any.whl").write_bytes(b"baz-wheel")
    return index


def test_dump_without_copy(tmp_path: Path) -> None:
    index = _make_local_layout(tmp_path)
    out = tmp_path / "out"

    result = dump_static(LocalRepository(index), out)

    assert result.project_count == 2
    assert result.file_count == 2
    assert result.referenced_bytes == len(b"wheel-bytes") + len(b"baz-wheel")

    assert (out / "simple" / "index.html").is_file()
    assert (out / "simple" / "foo-bar" / "index.html").is_file()
    assert (out / "simple" / "baz" / "index.html").is_file()
    assert not (out / "packages").exists()

    page = (out / "simple" / "foo-bar" / "index.html").read_text()
    assert f'href="file://{index}/foo-bar/foo_bar-1.0-py3-none-any.whl' in page


def test_dump_with_copy(tmp_path: Path) -> None:
    index = _make_local_layout(tmp_path)
    out = tmp_path / "out"

    result = dump_static(LocalRepository(index), out, copy_resources=True)

    assert result.project_count == 2
    assert result.file_count == 2
    assert result.referenced_bytes == len(b"wheel-bytes") + len(b"baz-wheel")
    # repo_bytes includes the copied files plus every index page.
    assert result.repo_bytes > result.referenced_bytes

    wheel = out / "packages" / "foo-bar" / "foo_bar-1.0-py3-none-any.whl"
    assert wheel.read_bytes() == b"wheel-bytes"

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


def test_cli_metadata_injector_adds_core_metadata_attribute(tmp_path: Path) -> None:
    dist = _make_flat_dist(tmp_path)
    out = tmp_path / "out"

    cli_main(["--output", str(out), str(dist)])

    page = (out / "simple" / "foo-bar" / "index.html").read_text()
    # MetadataInjectorRepository advertises PEP 658 metadata for every wheel.
    assert 'data-core-metadata="true"' in page


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
