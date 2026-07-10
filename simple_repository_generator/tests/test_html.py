"""
Tests for the human-friendly HTML serializer.

The compat surface is the PEP 503 `<a>` element: pip/uv only key off
`<a>` tags, so we assert byte-for-byte parity of the anchor set with
`simple_repository.serializer.SerializerHtmlV1`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser

import pytest
from simple_repository import model
from simple_repository.serializer import SerializerHtmlV1

from simple_repository_generator import __version__
from simple_repository_generator._html import (
    render_project_list,
    render_project_page,
)


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str | None]] = []
        self._in_a: dict[str, str | None] | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._in_a = {"__attrs__": None, **{k: v for k, v in attrs}}
            self._text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_a is not None:
            self._in_a["__text__"] = "".join(self._text_parts)
            self.anchors.append(self._in_a)
            self._in_a = None

    def handle_data(self, data: str) -> None:
        if self._in_a is not None:
            self._text_parts.append(data)


def _anchors(html_str: str) -> list[dict[str, str | None]]:
    p = _AnchorCollector()
    p.feed(html_str)
    return p.anchors


@pytest.fixture
def sample_page() -> model.ProjectDetail:
    files = (
        model.File(
            filename="foo-1.0-py3-none-any.whl",
            url="https://example.com/foo-1.0-py3-none-any.whl",
            hashes={"sha256": "aa" * 32},
            requires_python=">=3.11",
            dist_info_metadata=True,
            size=2048,
            upload_time=datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc),
        ),
        model.File(
            filename="foo-1.0.tar.gz",
            url="https://example.com/foo-1.0.tar.gz",
            hashes={"sha256": "bb" * 32},
            size=1500,
        ),
        model.File(
            filename="foo-0.9-py3-none-any.whl",
            url="https://example.com/foo-0.9-py3-none-any.whl",
            hashes={"sha256": "cc" * 32},
            yanked="stale build",
            size=1024,
        ),
    )
    return model.ProjectDetail(
        meta=model.Meta("1.1"),
        name="foo",
        files=files,
    )


def test_anchor_set_matches_serializer_html_v1(sample_page: model.ProjectDetail) -> None:
    ours = _anchors(render_project_page(sample_page))
    theirs = _anchors(SerializerHtmlV1().serialize_project_page(sample_page))

    # Same number of anchors and same order.
    assert len(ours) == len(theirs) == len(sample_page.files)

    keys = ("href", "data-requires-python", "data-core-metadata",
            "data-yanked", "data-gpg-sig", "__text__")
    for o, t in zip(ours, theirs):
        for k in keys:
            assert o.get(k) == t.get(k), f"attr {k!r} differs: {o!r} vs {t!r}"


def test_no_extraneous_anchors_on_project_page(sample_page: model.ProjectDetail) -> None:
    # pip parses every <a href> as a distribution candidate.  Any non-file
    # anchor would poison the index.
    anchors = _anchors(render_project_page(sample_page))
    assert len(anchors) == len(sample_page.files)


def test_no_extraneous_anchors_on_project_list() -> None:
    page = model.ProjectList(
        meta=model.Meta("1.1"),
        projects=(
            model.ProjectListElement(name="foo"),
            model.ProjectListElement(name="Bar-Baz"),
        ),
    )
    anchors = _anchors(render_project_list(page))
    # Exactly one anchor per project, nothing extra.
    assert len(anchors) == 2
    assert anchors[0]["href"] == "foo/"
    assert anchors[1]["href"] == "bar-baz/"


def test_generator_meta_present(sample_page: model.ProjectDetail) -> None:
    html_str = render_project_page(sample_page)
    assert (
        f'<meta name="generator" content="simple-repository-generator/{__version__}">'
        in html_str
    )


def test_xss_in_filename_is_escaped() -> None:
    # A filename containing HTML metacharacters must never land in the page
    # verbatim - not in the anchor text, not anywhere else.
    evil = "<script>alert(1)</script>-1.0.tar.gz"
    page = model.ProjectDetail(
        meta=model.Meta("1.1"),
        name="pwn",
        files=(
            model.File(
                filename=evil,
                url="https://example.com/x.tar.gz",
                hashes={"sha256": "de" * 32},
                size=1,
            ),
        ),
    )
    html_str = render_project_page(page)
    assert "<script>alert(1)</script>-1.0.tar.gz" not in html_str
    assert "&lt;script&gt;alert(1)&lt;/script&gt;-1.0.tar.gz" in html_str


def test_xss_in_project_name_is_escaped() -> None:
    page = model.ProjectList(
        meta=model.Meta("1.1"),
        projects=(model.ProjectListElement(name="<img src=x>"),),
    )
    html_str = render_project_list(page)
    assert "<img src=x>" not in html_str
    assert "&lt;img src=x&gt;" in html_str


def test_progressive_enhancement_script_present(
    sample_page: model.ProjectDetail,
) -> None:
    html_str = render_project_page(sample_page)
    assert "fetch(" in html_str
    assert "data-core-metadata" in html_str


def test_yanked_file_is_flagged(sample_page: model.ProjectDetail) -> None:
    html_str = render_project_page(sample_page)
    assert "yanked: stale build" in html_str


def test_file_size_is_human_readable(sample_page: model.ProjectDetail) -> None:
    html_str = render_project_page(sample_page)
    assert "2.0 KiB" in html_str


def test_upload_time_is_rendered(sample_page: model.ProjectDetail) -> None:
    html_str = render_project_page(sample_page)
    assert "2026-07-09" in html_str
