# F-Pn, Vma ms 1067 — volume-level material

Material that belongs to the whole volume rather than to any one work in it, kept out of the
item folders on purpose: `audit_contents.py` sums every PDF in an item folder to get its page
count, so a five-page booklet sitting beside a 24-page quartet would report 29 and could
flag the item as the wrong length.

This directory holds no `metadata.json`, so it is not an item and no consumer counts it.

| file | |
|---|---|
| `Vma-1067-facsimile-booklet.pdf` | 5 pp. Presentation facsimile of the volume, built by the upstream pipeline's `make_booklet.py` from Melissa's photographs. |

## The six works themselves

One folder each, filed under their Gérard numbers — `G228`, `G229`, `G230`, `G231` (Op. 48
nos. 3–6) and `G248`, `G249` (Op. 64 nos. 1–2). Each carries its own copy of `page-index.md`
and `derivation.json`, mapping every page back to the photograph it came from.

```sh
uv run boc.py find "F-Pn Vma ms 1067"
```

The booklet is derived and rebuildable upstream, so it is not declared in `originals.jsonl`.
The photographs it was built from are the irreplaceable thing, and they live outside this
archive — see any of the six item READMEs.
