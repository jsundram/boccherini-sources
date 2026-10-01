# Intake: what an upstream pipeline should produce

For a pipeline that builds PDFs from raw photographs and wants them to land in this archive
with search working. There are two ways in, and the second is cheaper.

**The authority is code, not this document.** `tools/check_intake.py` holds the field table
and `tools/adapt_intake.py` holds the mapping. If this file disagrees with either, this file
is wrong. Print the machine-readable version with:

```sh
uv run tools/check_intake.py --spec
```

## The cheap way: emit `derivation.json` and let the archive resolve RISM

Your pipeline knows what it photographed. It does not know RISM, and it should not have to —
the cache lives here. Emit a `derivation.json` beside the PDFs and run the adapter:

```sh
uv run tools/adapt_intake.py <your-output-dir> --report   # what it would resolve, and why
uv run tools/adapt_intake.py <your-output-dir>            # copy in and write metadata
```

```jsonc
{
  "collection": {
    "shelfmark":    "F-Pn, Vma ms 1067",       // the volume, as the library writes it
    "repository":   "Bibliothèque nationale de France, Département de la Musique",
    "city":         "Paris",
    "photographer": "Melissa",
    "photo_date":   "2026-04-09",
    "siglum":       "F-Pn"                     // optional: resolved from `repository`
  },
  "quartets": [
    {
      "id":     "1067-1",                      // trailing number is the volume position
      "pdf":    "…(1).pdf",                    // filename; its *words* are never trusted
      "title":  "Quartettino N.o 1",
      "opus":   "Op. 48",
      "dated":  "Madrid, giugno 1794",         // ← the one field that does the work
      "gerard": null,                          // optional; verified, never trusted
      "parts":  {"Violino 1°": "49-53", "Violino 2°": "70-74", "Alto": "…", "Violoncello": "…"}
    }
  ],
  "pages": [{"page": 3, "photo": "…jpg", "sha256": "…"}]
}
```

### Why `dated` and not the filename

The `Vma ms 1067` PDFs arrived named *Opus 48 Number 1* through *Number 4*. Those are
positions in a volume holding four of the six quartettini — the pieces are Op. 48 **nos. 3–6**.
Op. 48 is one quartettino per alternate month of 1794, so the date the manuscript carries
identifies it and the filename does not:

    febraro=226  aprile=227  giugno=228  agosto=229  ottobre=230  decembre=231

The adapter matches your `dated` against RISM's own title for each source at that shelfmark
and records the reasoning in `gerard_corroborated_by`. Four of the six resolved that way; the
two Op. 64 quartets carried an explicit `gerard`, which it checked against RISM rather than
believing. If a quartet has neither `dated` nor `gerard` and the shelfmark holds more than
one candidate, it is reported unresolved and nothing is written for it.

## The direct way: write `metadata.json` yourself

One folder per work, `digitizations/G<label>/<rism_source_id>_<siglum>/`, holding the PDF
named `<folder>.pdf`. Then validate before building:

```sh
uv run tools/check_intake.py <folder>       # errors block, warnings name what degrades
```

**Required** — every item in the archive carries these and consumers break without them:

| field | | why |
|---|---|---|
| `siglum` | `"F-Pn"` | Half the search key. A holding with no siglum is skipped by the concordance. |
| `title` | | Shown everywhere. |
| `source` | `"private-photography"` | Where it came from: a portal name, a RISM URL, or this. |

**Wanted** — each omission costs something specific, and the validator says which:

| field | | why |
|---|---|---|
| `shelfmark` | `"Vma ms 1067 (1)"` | The other half of the search key. **Must contain a digit** — `concordance.norm()` discards it otherwise and the item becomes findable by RISM id only. RISM's own `[no indication]` placeholder is accepted as such. |
| `source_id` | `"840022755"` | RISM's id for *this copy*. Lets the concordance answer definitively instead of inferring from a shelfmark, which is not always one object. |
| `rism_relation` | `"copy"` | The only value read as a claim to hold that source. `"work"` means the record is for the same music **elsewhere** and is deliberately not a holding claim. |
| `gerard`, `gerard_numbers`, `gerard_label` | `"228"`, `["228"]`, `"228"` | **Strings, not ints** — an int breaks `gnum()`. The label names the folder. |
| `institution` | | Lets a citation that spells the library out resolve to the siglum. |
| `medium` | `print` \| `manuscript` \| `autograph` | |
| `form` | `quartet` \| `not-a-quartet` | If `not-a-quartet`, `not_quartet_reason` is required. |
| `parts` | `["violin1","viola",…]` | Part **names**, or a `{name: file}` map. An int here crashed the shelf build. |
| `arrived_as` | `"pdf"` | Say this when the item was supplied as a finished PDF, or `boc check` asks for a `page_index` recording what page-image filenames meant — and there were none. |
| `url` / `manifest` / `ark` / `mets` | | A way back. **An item with none must be declared** (below), or `boc check` fails. |

## Anything that exists nowhere else

An item with no re-fetchable address needs a checksum instead of a URL:

```sh
uv run boc.py protect --declare <folder> --from "who gave it to you"
```

`boc check` then verifies every byte on every run and the destructive tools skip the folder.
See the *Scans that exist nowhere else* section of `CLAUDE.md`.

If your pipeline already records a `sha256` per source photograph — the BnF one does — keep
it in `derivation.json`. The adapter copies that file in beside the PDF, so the chain from
photograph to page survives in the archive.

## Then

```sh
uv run boc.py build && uv run boc.py check
```
