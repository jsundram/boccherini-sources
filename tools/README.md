# tools/

Implementation. **Call `uv run boc.py` from the repository root instead** — it wraps what a
session needs and rebuilds what a change invalidates. These live here so the root holds one
runnable thing, and so reaching past the front door takes a deliberate act.

Anything here may be run directly when you know why. The hazard is not that they are
fragile; it is that several *write* to the archive and the ordering between them is real.
`pipeline.py` declares that ordering; running a stage alone skips it.

## The pieces

| | |
|---|---|
| `check_intake.py` | does a folder meet the intake spec? the field table is the authority, not the prose |
| `adapt_intake.py` | turns an upstream pipeline's output into archive-shaped items, resolving RISM from what the manuscript says about itself |
| `originals.py` | scans that exist nowhere else: declare them, verify every byte, list them |
| `pipeline.py` | declares every stage, what it reads and writes; runs what is stale, propagates dirtiness downstream |
| `check_archive.py` | the invariants. The last word on whether the archive means what the documents say |
| `evidence.py` | one definition of what stands behind a label (tiers A–F), imported by the shelf, the concordance and the audit |
| `claim.py` | the only validated way to write a label or a linkage |
| `stats.py` · `state_of_evidence.py` | generate every number that appears in a document |

### Acquisition — network, occasional

`rism_digitizations.py` (harvest + download), `rism_incipits.py`, `find_scans.py` (Gallica
search), `parse_portal_results.py` (read a browser-saved search page).

### Enrichment — run by the pipeline

`normalize_metadata.py`, `preserve_page_labels.py`, `collate_pdfs.py`, `verify_pdfs.py`,
`read_structure.py` (OCR).

### Derivation — read everything, write reports

`concordance.py`, `audit_contents.py`, `compare_rism.py`, `suggest_ids.py`.

### Presentation

`build_sources_page.py` (the shelf), `build_page.py` (the incipit table),
`build_review_page.py` + `apply_review.py` (the review queue and its return path),
`contact_sheet.py` (look at one item).

## Two subdirectories

**`oneoff/`** — jobs that have been done. They are kept as a record of how, not as tools to
reach for. One of them deletes things.

**`mei/`** — `incipit_convert.py` and its tests: a Plaine & Easie → MEI → MusicXML converter
with a round-trip harness. A separate piece of research that shares this repository and
touches none of the archive.
