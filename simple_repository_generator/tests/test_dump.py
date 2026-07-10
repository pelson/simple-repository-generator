"""
Tests for dump_static.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from simple_repository.components.local import LocalRepository

from simple_repository_generator import dump_static
from simple_repository_generator.__main__ import main as cli_main


def _make_fixture_index(root: Path) -> Path:
    """LocalRepository layout: <index>/<normalized-name>/<file>."""
    index = root / "index"
    (index / "foo-bar").mkdir(parents=True)
    (index / "foo-bar" / "foo_bar-1.0-py3-none-any.whl").write_bytes(b"wheel-bytes")
    (index / "foo-bar" / "foo_bar-1.0.tar.gz").write_bytes(b"sdist-bytes")
    (index / "baz").mkdir(parents=True)
    (index / "baz" / "baz-0.1-py3-none-any.whl").write_bytes(b"baz-wheel")
    return index


def test_dump_without_copy(tmp_path: Path) -> None:
    index = _make_fixture_index(tmp_path)
    out = tmp_path / "out"

    result = dump_static(LocalRepository(index), out)

    assert result.project_count == 2
    assert result.file_count == 3
    assert result.copied_bytes == 0

    assert (out / "index.html").is_file()
    assert (out / "simple" / "foo-bar" / "index.html").is_file()
    assert (out / "simple" / "baz" / "index.html").is_file()
    assert not (out / "packages").exists()

    # Without --copy hrefs point at the source file:// URLs.
    page = (out / "simple" / "foo-bar" / "index.html").read_text()
    assert f'href="file://{index}/foo-bar/foo_bar-1.0-py3-none-any.whl' in page


def test_dump_with_copy(tmp_path: Path) -> None:
    index = _make_fixture_index(tmp_path)
    out = tmp_path / "out"

    result = dump_static(LocalRepository(index), out, copy_resources=True)

    assert result.project_count == 2
    assert result.file_count == 3
    assert result.copied_bytes == (
        len(b"wheel-bytes") + len(b"sdist-bytes") + len(b"baz-wheel")
    )

    wheel = out / "packages" / "foo-bar" / "foo_bar-1.0-py3-none-any.whl"
    assert wheel.read_bytes() == b"wheel-bytes"

    page = (out / "simple" / "foo-bar" / "index.html").read_text()
    # href is a relative path from the page to the copied wheel.
    assert 'href="../../packages/foo-bar/foo_bar-1.0-py3-none-any.whl' in page
    assert "file://" not in page


def test_index_lists_all_projects(tmp_path: Path) -> None:
    index = _make_fixture_index(tmp_path)
    out = tmp_path / "out"
    dump_static(LocalRepository(index), out)

    index_html = (out / "index.html").read_text()
    assert "foo-bar" in index_html
    assert "baz" in index_html


def test_cli_refuses_http_source(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="HTTP sources are not supported"):
        cli_main(["--output", str(tmp_path / "out"), "https://pypi.org/simple/"])


def test_cli_refuses_nonempty_output_without_force(tmp_path: Path) -> None:
    index = _make_fixture_index(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "leftover").write_text("x")

    with pytest.raises(SystemExit, match="not empty"):
        cli_main(["--output", str(out), str(index)])


def test_cli_writes_and_prints_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    index = _make_fixture_index(tmp_path)
    out = tmp_path / "out"

    cli_main(["--output", str(out), "--copy", str(index)])

    captured = capsys.readouterr().out
    assert "projects:     2" in captured
    assert "distributions:   3" in captured
    assert "copied bytes:" in captured
    assert (out / "packages" / "baz" / "baz-0.1-py3-none-any.whl").is_file()
