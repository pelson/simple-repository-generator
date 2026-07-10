# simple-repository-generator

Generate a static [PEP 503](https://peps.python.org/pep-0503/) HTML index from
local directories of wheels and sdists, or from an existing HTTP simple
index. The output tree is a plain set of files suitable for uploading to
GitHub Pages, S3, or any other static host.

Built on [`simple-repository`](https://github.com/simple-repository/simple-repository).

## Install

```
pip install simple-repository-generator
```

## CLI

```
simple-repository-generator [--output OUT] [--copy] [--force] SOURCE [SOURCE ...]
```

- `SOURCE`: either a local directory (crawled recursively for wheels and
  sdists) or an HTTP simple-index URL. Multiple sources are collapsed via
  `PrioritySelectedProjectsRepository`: the first source listed wins on
  conflicts.
- `--output OUT`: destination directory (default `./build/simple-repo`).
- `--copy`: copy distribution files into the output tree and rewrite
  hrefs to relative paths, producing a self-contained tree. Without
  `--copy`, hrefs point at the source (a `file://` URL for a local
  directory, or the upstream URL for an HTTP source).
- `--force`: allow writing into a non-empty output directory.

Local sources do not need to be pre-arranged: filenames are parsed per
PEP 427 (wheels) and PEP 625 (sdists) to infer the project name, and files
are grouped accordingly. Anything whose name doesn't parse is skipped.

### Example

```
$ simple-repository-generator --copy dist/
Wrote simple index to build/simple-repo
  sources:      dist/
  projects:     1
  files:        2
  repo size:    2.8 KiB
  referenced:   2.0 KiB
```

Output tree:

```
build/simple-repo/
  simple/
    index.html                                          # project list
    tiny-pkg/
      index.html                                        # project page
  packages/
    tiny-pkg/
      tiny_pkg-0.1.0-py3-none-any.whl
      tiny_pkg-0.1.0-py3-none-any.whl.metadata          # PEP 658 sidecar
      tiny_pkg-0.1.0.tar.gz
```

Point pip or uv at the `simple/` subdirectory:

```
pip install --index-url https://you.github.io/repo/simple/ tiny-pkg
```

### Metadata exposed to clients

The emitted project pages carry every attribute the source repository
provides: `data-requires-python`, `data-yanked`, `data-gpg-sig`. In
addition, the generator wraps the source in `MetadataInjectorRepository`,
which advertises `data-core-metadata="true"` on every wheel. In `--copy`
mode the corresponding `.metadata` sidecar file (extracted from each
wheel's `*.dist-info/METADATA`) is written alongside the wheel, so pip
and uv can resolve dependencies without downloading the wheel itself.

File size and upload time are recorded in the `File` model and appear in
the JSON representation. The HTML PEP 503 index does not carry a
data-size attribute (that field is JSON-only in PEP 691), so it is not
surfaced in the emitted HTML.

## Library API

```python
from pathlib import Path
from simple_repository.components.local import LocalRepository
from simple_repository_generator import dump_static

repo = LocalRepository(Path("dist"))
result = dump_static(repo, Path("build/simple-repo"), copy_resources=True)
print(result.project_count, result.file_count, result.repo_bytes)
```

`dump_static` accepts any `SimpleRepository`, so you can compose sources
with `simple-repository`'s existing components before serializing.

## Possible future extensions

- A JSON simple-index emitter (PEP 691) for hosts that can serve the
  registered vendor MIME types (e.g. S3, nginx). Pip enforces MIME
  strictly, so this is unusable on GitHub Pages today.
- Allow-list / deny-list / merge composition on the CLI, once HTTP
  sources make config-file input worthwhile.
- Recording `data-size` / upload-time in whatever future PEP extends
  HTML with those attributes.
- Incremental / retention-aware builds. Each run currently writes a
  fresh tree.
