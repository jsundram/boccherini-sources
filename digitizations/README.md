# Boccherini string quartets — the digitization archive

<!-- stats:storage -->
**144 folders, 230 files** (230 PDFs). Page images live inside the collated PDFs; see `PAGE-IMAGES-AND-PDFS.md`.
<!-- /stats:storage -->
three items that are marked as not being quartets at all.

Stored by Gérard number. Each folder holds the images or PDFs, a `metadata.json` recording
where it came from and how it was identified, and a `README.md` in prose.

---

## The documents, and which question each answers

### What we have

| file | answers |
|---|---|
| **`INDEX.md`** | Every MARC 856 link RISM publishes, by Gérard number — the harvest ledger |
| **`inventory.jsonl`** | The same, one JSON row per link, for querying |
| **`../boccherini_sources.html`** | The shelf: every item on disk, browsable — published at <https://claude.ai/artifact/YbGE1XtRkKt26BQahVtgMH> |
| **`../boccherini_incipits.html`** | Every incipit RISM publishes, as notation — published at <https://claude.ai/artifact/YNBZd5PduJBFr3t6KnWqWR> |
| **`STATE-OF-EVIDENCE.md`** | What supports each item's label, and what still needs eyes |
| **`RISM-DISAGREEMENTS.md`** | Items whose medium disagrees with RISM's source type |
| **`EVIDENCE-CHAIN.md`** | Where each fact comes from, which layer wins, how to correct it |
| **`AUTOMATION.md`** | What content checking can be automated, measured |
| **`CONTENT-AUDIT.md`** | Does the disk match the label? What has been checked, and what to look at next |
| **`TO-IDENTIFY.md`** | Folders with images and no Gérard number. **Currently empty.** |
| **`CONCORDANCE.md`** | Citation → RISM source → what we hold, indexed by library. Built by `../concordance.py`, which also resolves citations from the command line. |

### What exists but we do not have

| file | answers |
|---|---|
| **`UNLINKED-HOLDINGS.md`** | 1,344 holdings RISM catalogues with no scan link, by library. The `got` column marks the 50 we hold anyway. **Start here** — the autograph table is at the top. |
| **`MANUAL-DOWNLOADS.md`** | items no script can reach |
| **`PORTAL-SURVEY.md`** | 169 library portals, and whether each is worth trying |
| **`GALLICA-SEARCH.md`** · **`PORTAL-FINDS.md`** | What portal searching turned up |

### Library by library

| file | answers |
|---|---|
| **`BERLIN-FINDINGS.md`** | D-B: all 74 digitized items checked. Quartets exhausted. What the outstanding `KHM` shelfmarks actually are. |
| **`BNE-TODO.md`** | E-Mn: **complete** — 12 filed, 2 deliberately skipped, 0 outstanding |
| **`OPUS-58-AND-CARMIRELLI.md`** | Op. 58, and why the Ricordi edition cannot be linked to RISM |
| **`PRIOR-PASS-AUDIT.md`** | The earlier download passes: what was already held, what was new |
| **`PAGE-IMAGES-AND-PDFS.md`** | Why the scans are PDFs now, where the JPEGs went, how to get one back |
| **`PDF-VERIFICATION.md`** | The proof: 3,833 pages, 0 failures |

### Letters to send

`MUENSTER-REQUEST.md` — D-MÜs `SANT Hs 531`, the one autograph worth paying for.
`STAMS-REQUEST.md` — A-ST, nine manuscripts.
`UDK-REQUEST.md` — D-Bhm `RH 0322`. Still sendable, but read the note at the top first:
it is a 1905 copy, not an autograph, so do not ask for it as one.

---

## Verify before you trust

```sh
uv run boc.py check
```

Asserts what this archive is supposed to hold: every folder identified or marked
not-a-quartet, every folder reaching RISM or listed as a known exception, `rism_related`
always a list, no loose images without a collated PDF, no PDF shorter than the images
beside it, a `page_index` wherever filenames were discarded, and all three harvester
download paths still guarded. Each check is there because that thing went wrong once.

## Two things that will bite you

**Hand edits to a folder's `metadata.json` half-survive, and the half matters.** The
harvester rebuilds a sidecar from RISM on every run. It now *merges* — fields it does not
produce are carried over — so `publisher`, `rism_related` and `page_index` persist. But the
**folder name** is still rebuilt from RISM, and `relocate()` will move a folder back if its
Gérard numbers came from a hand edit rather than from `corrections.json`. Two folders were
silently reverted before this was noticed: `KHM 577` and the D-LEm volume, both of which
RISM gives no Gérard number.

So: a Gérard number established by looking at a scan goes in **`corrections.json`**, keyed
by RISM source id. Derived enrichment goes in a script that can be re-run —
`normalize_metadata.py`, `preserve_page_labels.py`. Nothing important should exist only as
a manual edit to a sidecar.

**RISM's scoring field decides what counts as a quartet**, and when it is empty the uniform
title is consulted instead — in whichever language the cataloguer used. `Quatuors` outnumbers
`Quartets` two to one among the scoring-less records, and matching only the English form hid
**ten F-Po autographs** until it was fixed. The fallback now also demands a Gérard number,
and drops single-movement extracts unless the source is an autograph.

---

## Running it

```sh
uv run tools/rism_digitizations.py --download --full   # harvest, download, regenerate the indexes
uv run tools/rism_incipits.py > boccherini-rism-incipits.jsonl
uv run tools/suggest_ids.py                            # propose Gérard numbers for anything unidentified
uv run tools/build_sources_page.py                     # rebuild the shelf
uv run tools/parse_portal_results.py <saved.html> --stage BNE
uv run tools/normalize_metadata.py                     # fill publisher / RISM links from RISM itself
uv run tools/collate_pdfs.py                           # one PDF per item (idempotent)
uv run tools/verify_pdfs.py --report                   # prove the PDFs hold the original bytes
```

Re-running downloads nothing it already has.

## Where the material comes from

| siglum | library | folders |
|---|---|---:|
| D-B | Staatsbibliothek zu Berlin | 43 |
| F-Pn | BnF, Musique | 30 |
| US-R | Rochester | 18 |
| E-Mn | Biblioteca Nacional de España | 13 |
| F-Po | Bibliothèque-Musée de l'Opéra | 8 |
| D-Eu | Eichstätt | 6 |
| D-Mbs | Munich | 4 |
| F-Pc | Conservatoire | 3 |

## What is actually still missing

Read the autograph table at the top of `UNLINKED-HOLDINGS.md`. **12 autograph holdings are
still open**, and ten of them are one run of shelfmarks: F-Po `RES-507 (3)`–`(9)`, `(12)`,
`(13)`, `(15)` — the monthly *quartettini* of 1789–1794. Every neighbouring number in that
run is on Gallica, so these are likely downloadable rather than letter-writing targets.

The other two are D-Bhm `RH 0322` (which is a 1905 copy, so not really an autograph) and
D-MÜs `SANT Hs 531`, which is the one genuinely worth ordering.
