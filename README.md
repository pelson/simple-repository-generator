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
  repo size:    2.9 KiB (13.7 KiB in output directory)
```

Output tree:

```
build/simple-repo/
  simple/
    index.html                                          # project list
    some-project/
      index.html                                        # project page
  packages/
    some-project/
      some_project-0.1.0-py3-none-any.whl
      some_project-0.1.0-py3-none-any.whl.metadata          # PEP 658 sidecar
      some_project-0.1.0.tar.gz
```

Point pip or uv at the `simple/` subdirectory. Any URL scheme pip
supports for `--index-url` works, including `file://` for a local
sanity check (the path after `file://` must be absolute):

```
pip install --index-url "file://$(pwd)/build/simple-repo/simple/" some-project
```

The output is a plain directory of static files, so it drops straight
into a GitHub Pages site, an S3 bucket, or anything served by
`python -m http.server`.

### Metadata exposed to clients

The emitted project pages carry every attribute the source repository
provides: `data-requires-python`, `data-yanked`, `data-gpg-sig`. In
`--copy` mode the generator additionally wraps the source in
`MetadataInjectorRepository`, extracts each wheel's `*.dist-info/METADATA`
into a `.metadata` sidecar next to the copied wheel, and advertises
`data-core-metadata="true"` on the page, so pip and uv can resolve
dependencies without downloading the full wheel.

Without `--copy` the pages are passed through unchanged. In particular
`data-core-metadata` is not injected, because there is no matching
`.metadata` file to serve alongside the source URL.

The emitted HTML is also designed to be human-friendly to browse
directly, with file size, upload date and other metadata surfaced
outside the PEP 503 anchor set. Machine clients (pip, uv) only look at
the `<a>` elements, which stay strictly PEP 503 compliant.

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
