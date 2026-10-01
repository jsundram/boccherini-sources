# How much of the content checking can be automated

Short answer: **the structure of an engraved print, mostly. Nothing about a manuscript.**

Measured on items whose contents were established by eye first, so the numbers mean
something.

## What works

**Part-book boundaries, on engraved prints.** `read_structure.py` OCRs the top eighth of
every page and reads the part name from it. On Op. 58 livraison 2 it found four part-books
at pages 5, 23, 37, 47 — the same four, at the same pages, that a contact sheet shows. On
Rochester's Op. 2 it named all four correctly from the concatenated part PDFs. This is the
answer to *"parts or score, and how many parts"*, which is the question most prints do not
state anywhere.

**Tempo markings.** Read cleanly off engravings: `Allegro Molto`, `Andante Sostenuto`,
`Allegretto Moderato` — all three correct on Op. 58 livraison 2.

**Work-start pages.** On a well-engraved print, the pages where a new quartet begins are
found: livraison 2 gave p5, p11, p17, which is exactly right.

**Narrowing to a Gérard number.** RISM's incipits carry a tempo caption per movement:

- **80 of 82** Gérard numbers have a **unique** (tempo, key, metre) first-movement signature
- **67 of 77** are unique on **tempo alone within their own opus**

So a tempo read off the page usually picks one candidate out of six. Where it does not, the
tool says *ambiguous* and lists them.

## What does not work

**Manuscripts.** OCR reads engraving, not handwriting. Berlin's `KHM 563` returns nothing at
all, and the F-Po Op. 33 autograph returns noise — every manuscript copy and every
autograph, permanently out of reach of this approach.

<!-- stats:ocr -->
- **78** items were read by OCR; **66** are manuscripts it cannot read
- medium: **10** autograph, **56** manuscript, **78** print
- **14** items whose pages disagree with their label
<!-- /stats:ocr -->

**Roman numerals.** `IV. QUATUOR` and the folio number in the corner look the same to OCR.
Reading the outer corners separately and subtracting their tokens helped — it got `IV`
right — but `V` and `VI` still came back as 7 and 5. Page numbers and work numbers are both
small roman numerals near the top of the page, and context is not enough to separate them
reliably. **Trust the page where a work starts, not the number printed on it.**

**Four of Pleyel's twelve.** G 213, 215, 233 and 235 have no RISM incipit at all, so no
tempo method can name them however well the OCR reads. They were identified by hand from
the scans, and that is the only way they could have been.

## What would need real OMR

Key signature, clef and the opening notes. That would close the remaining gap — it would
break the tempo ties, identify parts from their clef rather than their printed name, and
match incipits directly instead of by caption. Tools exist (Audiveris, oemer); none of this
has been tried here.

## How to use it

```sh
uv run tools/read_structure.py digitizations/<folder>      # proposal
uv run boc.py look  digitizations/<folder>      # look at it
```

Then record the answer, so nobody does it twice:

```json
"contents_verified": {"date": "...", "how": "...", "found": "..."}
```

`read_structure.py` proposes and never writes. Everything it prints is a starting point for
looking, not a substitute for it — which is the same rule that applies to the rest of this
archive.
