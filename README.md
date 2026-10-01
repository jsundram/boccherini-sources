# Boccherini's string quartets — sources, incipits, and scans

**Start with `uv run boc.py`.** It is the only script in the root; everything else lives in
`tools/` and is implementation. `CLAUDE.md` carries the working rules and loads
automatically in a Claude Code session.

```sh
uv run boc.py status      # where the archive stands
uv run boc.py todo        # what needs a person
uv run boc.py find "F-Po Rés. 507 (14)"
uv run boc.py build && uv run boc.py check
```

<!-- stats:headline -->
| | |
|---|---:|
| Items on disk | **144** |
| Incipits harvested | **643** |
| RISM quartet sources | **613** |
| Holdings RISM lists with no scan | **1344** at 144 libraries |
| Label rests on evidence | **82** of 144 |
| Still needs a person to look | **62** |
| Unidentified | **0** |
<!-- /stats:headline -->

Two published pages:

- **[Facsimile shelf](https://claude.ai/artifact/YbGE1XtRkKt26BQahVtgMH)** — every manuscript
  and early edition on disk, by opus, with an evidence badge on each
- **[Incipit table](https://claude.ai/artifact/YNBZd5PduJBFr3t6KnWqWR)** — every incipit RISM
  publishes, rendered as notation

---

## "I have a citation. What is it, and do we have it?"

```sh
uv run boc.py find "F-Po Rés. 507 (14)"
uv run boc.py find-file my-article.md     # every citation in a document
```

It takes citations however they are written — siglum and shelfmark, the library spelled out
in prose, a bare shelfmark, a RISM id, a Gérard number, an opus and number, a PPN, a Gallica
ark — and returns ranked candidates, each saying whether a scan is on disk and where.

```
Paris, Bibliothèque-Musée de l'Opéra, Rés. 507 (14)
   [100] G 228   840013721   Autograph manuscript   ✓ HELD G228/btv1b52502357c
         F-Po RES-507 (14)
         Mese di Giugno. 1794. | Quartettino. | Boccherini
```

Scores rank, they do not decide: a RISM id is 120, a siglum-plus-shelfmark 100, a Gérard
number alone 20 — because one Gérard number matches a dozen sources and you want to see all
of them.

`concordance.jsonl` is the same data, one row per RISM source, carrying every handle it has.
`digitizations/CONCORDANCE.md` is the readable form, indexed by library.

---

## Where to look

| you want | read |
|---|---|
| **What is solid and what is not** | **`digitizations/STATE-OF-EVIDENCE.md`** |
| Which layer a fact came from, and how to correct it | **`digitizations/EVIDENCE-CHAIN.md`** |
| Where our labels and RISM disagree | **`digitizations/RISM-DISAGREEMENTS.md`** |
| What is still open, and what it would settle | **`TODO.md`** |
| The whole story, decisions and mistakes included | **`STATUS.md`** |
| What is on disk and how it is organised | **`digitizations/README.md`** |
| A citation resolved | **`digitizations/CONCORDANCE.md`** |
| What exists that we do **not** have | **`digitizations/UNLINKED-HOLDINGS.md`** |
| What to chase next | the autograph table at the top of that file |

## The scripts

| script | does |
|---|---|
| `rism_incipits.py` | harvests incipits → `boccherini-rism-incipits.jsonl` |
| `rism_digitizations.py` | harvests MARC 856, downloads scans, writes every index |
| `concordance.py` | citation → RISM source → what we hold |
| `pipeline.py` | **the entry point** — runs every stage in dependency order |
| `claim.py` | **the only supported way** to change a label or a linkage |
| `stats.py` | fills the generated number blocks in the docs |
| `state_of_evidence.py` | generates what stands behind every label |
| `build_review_page.py` | the queue of items needing a person |
| `check_archive.py` | asserts the invariants, including that nothing is stale |
| `audit_contents.py` | does the disk match the label? ranks what to look at |
| `contact_sheet.py` | renders an item so its structure reads in one glance |
| `read_structure.py` | OCRs a print's own headings, stores the reading in `structure/` |
| `compare_rism.py` | checks our `medium` against RISM's own source type |
| `normalize_metadata.py` | fills publisher and RISM links from what RISM already says |
| `collate_pdfs.py` · `verify_pdfs.py` | one PDF per item, and the proof it is lossless |
| `preserve_page_labels.py` · `trash_collated_jpegs.py` | keep what filenames encoded, then reclaim the space |
| `suggest_ids.py` | proposes Gérard numbers for anything unidentified |
| `find_scans.py` | searches Gallica for scans RISM does not link |
| `survey_portals.py` | per-library verdict on whether a portal can be searched |
| `parse_portal_results.py` | reads a browser-saved search page into the archive |
| `build_page.py` · `build_sources_page.py` | the two published pages |

```sh
uv run boc.py build --check      # what is stale
uv run boc.py build              # bring everything up to date, in order
uv run boc.py build --skip harvest --skip read    # the fast path: no network, no OCR
```

**Use the pipeline rather than the individual scripts.** There are a dozen of them and the
order between them matters; it used to live only in somebody's memory, and the result was a
concordance published after its folders had moved and a shelf missing data added an hour
earlier. `pipeline.py` declares what each stage reads and writes, runs only what is stale,
and propagates dirtiness downstream. `check_archive.py` fails while anything is stale, so
"I forgot to re-run it" is no longer a way to ship something wrong.

---

## Changing a label or a linkage

**Use `claim.py`. It is the front door, and it is the only one.**

```sh
uv run boc.py label <folder> --gerard 242,243,244 --saw "what you actually saw"
uv run boc.py link  <folder> --rism 840013721 --relation copy --saw "..."
uv run boc.py confirm <folder> --saw "..."
uv run boc.py show  <folder>        # every claim on an item, and where each one lives
uv run boc.py build                    # then rebuild everything that depends on it
```

Two kinds of change matter and everything downstream trusts both: **labels** — what is in a
PDF — and **linkages** — which RISM record it is a copy of. They can be written in four
places with four precedences, so writing them by hand is how this archive acquired the
mistakes it has. `claim.py`:

- **refuses a Gérard number not in `opera.json`** and a RISM id not in the cache. A typo
  used to become a permanent, silent mislabel.
- **requires `--saw`** — what you observed. A claim with no evidence is a guess with a
  timestamp, and `check_archive.py` fails on labels that carry no provenance.
- **writes to the layer that owns the fact**: `corrections.json` when it belongs to the RISM
  record — the harvester rebuilds folder names from there, so a Gérard number written
  anywhere else is silently reverted on the next run — and `metadata.json` when it belongs
  to our copy.

Never hand-edit a sidecar. Never edit anything under `structure/`, or any file listed as a
stage output in `pipeline.py`; those are regenerated.

## Reviewing what needs eyes

```sh
uv run boc.py review                 # -> review.html; open, decide, export
uv run boc.py apply verdicts.json    # verdicts back in as validated claims
```

Every item the machines cannot settle, with its picture, what is claimed, what RISM says and
what the OCR read. Verdicts are kept in the browser and exported as one JSON file. The page
never edits the archive — decisions come back through `claim.py`, so every change is
validated and stamped the same way.

## Check the invariants before you trust anything

```sh
uv run boc.py check            # exits non-zero if something drifted
uv run boc.py check --verbose
```

Every check in that file exists because the thing it checks for actually went wrong. It is
the fastest way to find out whether the archive still means what the documents say it means.
Run it after any change, and especially after a harvest.

## Most of this metadata has never been checked against the pages

`digitizations/CONTENT-AUDIT.md` says how many items have. It is a small number. Everything
else carries metadata inherited from RISM, from a portal's search page, or from a filename
somebody typed — plausible, mostly right, and not verified.

```sh
uv run boc.py todo                      # what disagrees, ranked
uv run boc.py look digitizations/<folder>          # then look at it
uv run tools/read_structure.py digitizations/<folder>        # or let it propose first
```

How much of that is automatable is measured in `digitizations/AUTOMATION.md`: part-book
boundaries and tempo markings on **engraved prints**, yes; **manuscripts**, not at all — OCR
reads engraving, not handwriting. How many items that is, and what stands behind every
label, comes from `uv run boc.py status` — never from a number typed into a document.

`contact_sheet.py` stacks the top eighth of every page into one column. Printed part-books
announce themselves there — `IV. QUATUOR`, `VIOLINO I°`, `Andante Sostenuto` — so the
structure of a 70-page PDF reads in a glance. That is how Op. 58 was settled: two folders
both labelled G 242–247 turned out to be *"1re Partie"* and *"2e Partie"*, three quartets
each, which had been recorded as six quartets twice.

When you have read one, record it, so the next person does not repeat the work:

```json
"contents_verified": {"date": "2026-09-29", "how": "head-strip contact sheet",
                      "found": "quartets I-III in four part-books"}
```

## Ten things that will save you a day

**The harvester rebuilds every sidecar from RISM.** It now *merges* — keys it produces win,
everything else is carried over — but before that it overwrote, and silently deleted the
publisher parsed from a title imprint, the normalised `rism_related`, and the `page_index`
recording what the filenames said. If you add a field to `metadata.json`, confirm it
survives `uv run tools/rism_digitizations.py --download` before believing in it. Facts you
established by *looking at a scan* belong in **`corrections.json`**, keyed by RISM source id;
derived enrichment belongs in a script that can be re-run.

**There are three page-writing paths, not one** — the RISM-linked manifest loop, the
hand-found manifest loop, and a third for Muscat attachments and Rochester part files that
names by `Content-Disposition`. All three must call `pdf_is_complete()`. Guarding one and
not the others refetched 99 images before anyone noticed. `check_archive.py` counts the
call sites.

**Gérard is `GerB` in RISM**, in MARC 690 `$a`, linked to `publications/29` — not the word
"Gérard". Matching on the name returns nothing.

**RISM paginates unreliably.** Compare what you walked against `totalItems` and walk again
if they disagree. Three separate harvests silently returned short.

**Boccherini appears in RISM as a dedicatee.** Pleyel dedicated his Op. 9 to him, so thirteen
Pleyel prints come back from Boccherini's `/sources` endpoint. MARC 100 is the composer and
settles it — `by_composer()`. Before that check existed, 22 Pleyel incipits and 473 MB of
Pleyel scans were in the corpus.

**`[no indication]` is not a shelfmark.** RISM writes it for 679 holdings. Key on it and
every shelfmark-less holding at a library collapses into one — which is how Rochester's
folders were briefly credited to Madrid's shelfmark. `norm_shelf()` returns `''` for
anything with no digit in it, which is the cheapest correct fix.

**The publisher is usually in the title, not in `260 $b`.** RISM fills that subfield on 12
records corpus-wide; the imprint is instead the last bracketed phrase — *"... opera prima
[Amsterdam, J. J. Hummel]"*, sometimes several cities separated by semicolons, sometimes
`Berlin: Hummel` with a colon. `normalize_metadata.py` parses it.

**RISM numbers an anthology as a whole.** Pleyel's twelve-quartet *œuvre 39* carries a
single number, **G 234**, while our folders carry the livraison's own numbers, established
by hand from the scans. Any join demanding an exact Gérard-set match will miss all of them.

**One RISM record can be two books.** Op. 58 is a single RISM source, 990005886, for a
publication issued *en deux livraisons*. Berlin holds both, scanned separately; both folders
inherited the whole G 242–247 span, so two different books of three quartets each were
recorded as six quartets twice over. RISM publishes no incipits for Op. 58, so nothing
automatic could have caught it — the title pages did, in four words: *1re Partie*, *2e
Partie*.

**A shelfmark is not always one object, and a RISM id is not always the copy you hold.**
D-B `DMS 51778` covers ten of our folders, so resolving a source by shelfmark alone once
reported Pleyel's œuvre 39 as held at Op. 9 and Op. 15. `concordance.py` now answers at
three strengths — *this copy*, *the parent volume containing it*, *another copy of the same
edition* — and prefers an explicit id claim over any shelfmark match. Edition-level links
are deliberately excluded from the copy index; leaving them out of the lookup entirely made
**folders unreachable from RISM entirely**, which `check_archive.py` now guards against.

**Boccherini's title pages are formulaic.** *"Tre quartetti per due Violini, Viola e Basso"*
fits a dozen unrelated sources — on words alone the Library of Congress Op. 54 matched a
Naples manuscript of G 165. A title match needs a shared opus or œuvre number to mean
anything. Watch the minimum token length while you are at it: a 3-character floor drops
`39`, which is the entire point of *œuvre 39*.

## One habit worth keeping

`STATUS.md` has a section called **Corrections — things I asserted and had to retract**. It is
the most useful part of the file. The failures in this project were not missing data; they
were confident readings of data that said something else — a `593` saying "possible autograph"
over a `260` saying 1905, a scoring field trusted where it was simply empty. When you find one,
write it down there.
