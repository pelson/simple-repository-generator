"""
Human-friendly HTML rendering of PEP 503 index pages.

The emitted `<a>` elements carry exactly the same attributes as
`simple_repository.serializer.SerializerHtmlV1` produces, so pip, uv and
any other spec-compliant client see identical semantics. Everything else
on the page (tables, metadata columns, JS enhancement) sits outside the
`<a>` and is invisible to those clients.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Iterable

import packaging.utils
import packaging.version
from simple_repository import model

from ._version import __version__

_GENERATOR = f"simple-repository-generator/{__version__}"

_STYLE = """\
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
       sans-serif; margin: 2em auto; max-width: 60em; padding: 0 1em;
       color: #222; }
header h1 { margin-bottom: 0.1em; font-size: 1.6em; }
.subtitle { color: #666; margin-top: 0; font-size: 0.9em; }
table.files { border-collapse: collapse; width: 100%; font-size: 0.92em; }
table.files th, table.files td { padding: 0.35em 0.6em; text-align: left;
       border-bottom: 1px solid #eee; vertical-align: top; }
table.files th { background: #fafafa; font-weight: 600; }
table.files tbody tr:nth-child(even) { background: #fbfbfb; }
table.files tbody tr.metadata-row { background: inherit; }
table.files tbody tr.metadata-row > td { padding: 0.1em 0.6em 0.4em 2em;
       border-bottom: 1px solid #eee; }
table.files td.file a { font-family: ui-monospace, SFMono-Regular,
       Menlo, Consolas, monospace; text-decoration: none; color: #0645ad; }
table.files td.file a:hover { text-decoration: underline; }
tr.yanked td.file a { text-decoration: line-through; color: #a00; }
.yanked-reason { color: #a00; font-size: 0.85em; }
.missing { color: #bbb; }
ul.projects { list-style: none; padding: 0; }
ul.projects li { padding: 0.15em 0; }
ul.projects a { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
button.meta-toggle, .meta-toggle-spacer {
       display: inline-block; width: 1em; margin-right: 0.35em;
       text-align: center; vertical-align: middle; }
button.meta-toggle { background: none; border: none; padding: 0;
       cursor: pointer; color: #888; font: inherit; line-height: 1; }
button.meta-toggle::before { content: "\\25B8"; display: inline-block;
       transition: transform 0.1s ease; }
button.meta-toggle[aria-expanded="true"]::before { transform: rotate(90deg); }
button.meta-toggle:hover { color: #0645ad; }
pre.deps { background: #f5f5f5; padding: 0.6em; margin: 0;
       white-space: pre-wrap; font-size: 0.85em;
       max-height: 20em; overflow: auto; }
footer { margin-top: 2em; padding-top: 1em; border-top: 1px solid #eee;
       color: #888; font-size: 0.85em; }
footer .repo-url { font-family: ui-monospace, SFMono-Regular, Menlo,
       Consolas, monospace; }
"""

_SCRIPT = """\
(function () {
  // Upgrade the plain-text repository URL in the footer to a link.
  // We can only do this from JS: any <a href> on the page would be
  // treated by pip as a distribution candidate (PEP 503 clients only
  // key off <a> tags), so the server-rendered HTML keeps the URL as
  // text.
  document.querySelectorAll('span.repo-url[data-href]').forEach(function (el) {
    var a = document.createElement('a');
    a.href = el.getAttribute('data-href');
    a.textContent = el.textContent;
    el.replaceWith(a);
  });

  document.querySelectorAll('button.meta-toggle').forEach(function (btn) {
    var fileRow = btn.closest('tr');
    var metaRow = fileRow && fileRow.nextElementSibling;
    if (!metaRow || !metaRow.classList.contains('metadata-row')) return;
    var pre = metaRow.querySelector('pre.deps');
    var anchor = fileRow.querySelector('a[data-core-metadata]');
    if (!pre || !anchor) return;
    var loaded = false;
    btn.addEventListener('click', function () {
      var open = metaRow.hasAttribute('hidden');
      if (open) {
        metaRow.removeAttribute('hidden');
        btn.setAttribute('aria-expanded', 'true');
      } else {
        metaRow.setAttribute('hidden', '');
        btn.setAttribute('aria-expanded', 'false');
        return;
      }
      if (loaded) return;
      loaded = true;
      pre.textContent = 'loading...';
      fetch(anchor.href.split('#')[0] + '.metadata').then(function (r) {
        if (!r.ok) throw new Error('http ' + r.status);
        return r.text();
      }).then(function (body) {
        var interesting = [];
        var lines = body.split(/\\r?\\n/);
        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (line === '') break;
          if (/^(Summary|Requires-Python|Requires-Dist):/i.test(line)) {
            interesting.push(line);
          }
        }
        pre.textContent = interesting.length ? interesting.join('\\n')
                                             : '(no Requires-Dist)';
      }).catch(function () {
        pre.textContent = 'metadata unavailable';
      });
    });
  });
})();
"""


_MISSING = "-"


def _cell(value: str) -> str:
    """Escape a table cell value, muting the missing-data placeholder."""
    if value == _MISSING:
        return '<span class="missing">-</span>'
    return html.escape(value)


def _format_size(n: int | None) -> str:
    if n is None:
        return _MISSING
    if n < 1024:
        return f"{n} B"
    value = float(n)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        value /= 1024
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
    return f"{n} B"


def _format_upload_time(dt: datetime | None) -> str:
    if dt is None:
        return _MISSING
    return dt.strftime("%Y-%m-%d")


def _anchor_attributes(file: model.File) -> str:
    """Build the `<a>` attributes exactly as SerializerHtmlV1 does."""
    url = file.url
    if file.hashes:
        hash_fun = "sha256" if "sha256" in file.hashes else next(iter(file.hashes))
        url = f"{url}#{hash_fun}={file.hashes[hash_fun]}"

    attrs = [f'href="{url}"']

    if file.requires_python:
        attrs.append(
            f'data-requires-python="{html.escape(file.requires_python)}"',
        )

    if file.dist_info_metadata:
        if file.dist_info_metadata is True:
            attrs.append('data-core-metadata="true"')
        else:
            meta = file.dist_info_metadata
            hash_fun = "sha256" if "sha256" in meta else next(iter(meta))
            attrs.append(f'data-core-metadata="{hash_fun}={meta[hash_fun]}"')

    if file.yanked:
        if file.yanked is True:
            attrs.append('data-yanked=""')
        else:
            attrs.append(f'data-yanked="{file.yanked}"')

    if file.gpg_sig:
        attrs.append('data-gpg-sig="true"')
    elif file.gpg_sig is False:
        attrs.append('data-gpg-sig="false"')

    return " ".join(attrs)


def _render_file_row(file: model.File) -> str:
    anchor = (
        f"<a {_anchor_attributes(file)}>{html.escape(file.filename)}</a>"
    )
    size = _cell(_format_size(file.size))
    uploaded = _cell(_format_upload_time(file.upload_time))
    req_py = _cell(file.requires_python or _MISSING)

    notes: list[str] = []
    if file.yanked:
        reason = "" if file.yanked is True else str(file.yanked)
        label = "yanked" if not reason else f"yanked: {reason}"
        notes.append(f'<span class="yanked-reason">{html.escape(label)}</span>')
    if not notes:
        notes.append('<span class="missing">-</span>')

    if file.dist_info_metadata:
        toggle = (
            '<button type="button" class="meta-toggle" '
            'aria-expanded="false" '
            'aria-label="Show metadata"></button>'
        )
    else:
        toggle = '<span class="meta-toggle-spacer"></span>'

    row_class = ' class="yanked"' if file.yanked else ""
    main_row = (
        f"      <tr{row_class}>\n"
        f'        <td class="file">{toggle}{anchor}</td>\n'
        f'        <td class="size">{size}</td>\n'
        f'        <td class="uploaded">{uploaded}</td>\n'
        f'        <td class="requires-python">{req_py}</td>\n'
        f'        <td class="notes">{"".join(notes)}</td>\n'
        f"      </tr>\n"
    )
    if not file.dist_info_metadata:
        return main_row
    return main_row + (
        '      <tr class="metadata-row" hidden>\n'
        '        <td colspan="5"><pre class="deps"></pre></td>\n'
        '      </tr>\n'
    )


def _document(title: str, api_version: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f'  <meta name="pypi:repository-version" content="{html.escape(api_version)}">\n'
        f'  <meta name="generator" content="{html.escape(_GENERATOR)}">\n'
        f"  <title>{title}</title>\n"
        f"  <style>{_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "  <footer>\n"
        "    <p>Generated by "
        '<span class="repo-url" data-href="https://github.com/simple-repository/simple-repository-generator">'
        "simple-repository-generator</span> "
        f"{html.escape(__version__)}.</p>\n"
        "  </footer>\n"
        f"  <script>{_SCRIPT}</script>\n"
        "</body>\n"
        "</html>\n"
    )


class HumanFriendlyHtmlSerializer:
    """Serializer emitting PEP 503-compliant, human-readable HTML."""

    def serialize_project_page(self, page: model.ProjectDetail) -> str:
        name = html.escape(page.name)
        # Newest upload first; files without an upload_time land at the end.
        files = sorted(
            page.files,
            key=lambda f: (
                f.upload_time is None,
                -(f.upload_time.timestamp() if f.upload_time else 0),
            ),
        )
        rows = "".join(_render_file_row(f) for f in files)
        body = (
            "  <header>\n"
            f"    <h1>Files available for the {name} project</h1>\n"
            f'    <p class="subtitle">{len(page.files)} files</p>\n'
            "  </header>\n"
            '  <table class="files">\n'
            "    <thead>\n"
            "      <tr><th>File</th><th>Size</th><th>Uploaded</th>"
            "<th>Requires Python</th><th>Notes</th></tr>\n"
            "    </thead>\n"
            "    <tbody>\n"
            f"{rows}"
            "    </tbody>\n"
            "  </table>\n"
        )
        return _document(
            title=f"Files available for the {name} project",
            api_version=page.meta.api_version,
            body=body,
        )

    def serialize_project_list(self, page: model.ProjectList) -> str:
        items = "".join(
            '    <li><a href="{href}">{name}</a></li>\n'.format(
                href=html.escape(
                    packaging.utils.canonicalize_name(p.name) + "/",
                ),
                name=html.escape(p.name),
            )
            for p in page.projects
        )
        body = (
            "  <header>\n"
            "    <h1>Simple index</h1>\n"
            f'    <p class="subtitle">{len(page.projects)} projects</p>\n'
            "  </header>\n"
            '  <ul class="projects">\n'
            f"{items}"
            "  </ul>\n"
        )
        return _document(
            title="Simple index",
            api_version=page.meta.api_version,
            body=body,
        )


_SERIALIZER = HumanFriendlyHtmlSerializer()


def render_project_page(page: model.ProjectDetail) -> str:
    return _SERIALIZER.serialize_project_page(page)


def render_project_list(page: model.ProjectList) -> str:
    return _SERIALIZER.serialize_project_list(page)


__all__: Iterable[str] = (
    "HumanFriendlyHtmlSerializer",
    "render_project_page",
    "render_project_list",
)
