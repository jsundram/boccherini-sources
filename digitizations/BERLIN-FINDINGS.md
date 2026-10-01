# D-B, Staatsbibliothek zu Berlin — what is digitized and what is not

From the saved search of **`digital-beta.staatsbibliothek-berlin.de`**, filtered to
`structure_type=manuscript`, author `Boccherini, Luigi`.

**74 results, and that is the whole set** — the page was fetched with `results_on_page=100`
and returned 74, so there is no second page.

## The headline

**28 of the 74 are quartets. We already hold all 28.**

Berlin's digitized Boccherini quartet manuscripts are exhausted. The rest of the 74 are
quintets (Op. 25, 28–31, 36, 39, 42, 50), trios, symphonies, cello concertos, *La Clementina*,
and four *Schriftprobe* handwriting specimens — Boccherini's hand, but letters, not music.

## One identification came out of it

`KHM 577` — Berlin catalogues **PPN84753183X** as *"6 Quartette; vl (2), vla, vlc;
**G 201-206**; op.32"*. That is RISM [463057700](https://rism.online/sources/463057700), which
we had sitting in `unidentified/` with 161 pages and no Gérard number — **RISM gives none**.

Now filed as `G201-206/463057700_D-B`.

## The twelve shelfmarks that were outstanding

All twelve are real D-B manuscripts in RISM. **Eleven are not digitized** — none appears
anywhere in the 74 results. But they are not what an earlier draft of this file said they
were: RISM's own notes separate them into three different things.

### `KHM 569`, `570` — Op. **22**, not Op. 32

Both notes read *"Berliner Stimmensatz der Quartette **op. 22**"*. Two part-sets of Op. 22,
4 parts each. `KHM 570` carries G 183. We hold Op. 22 as `KHM 563`–`568`, so these are two
further Op. 22 part-sets.

### `KHM 571`–`576` — **scores**, one quartet each

| shelfmark | title | Gérard | extent |
|---|---|---|---|
| KHM 571 | Quartetto I.o | 201 | score: 16f. |
| KHM 572 | Quartetto II.o | 202 | score: 14f. |
| KHM 573 | Quartetto III.o | 203 | score: 18f. |
| KHM 574 | Quartetto IV.o | 204 | score: 16f. |
| KHM 575 | Quartetto V.o | 205 | score: 20f. |
| KHM 576 | Quartetto VI.o | 206 | score: 20f. |

All six are dated *"Opera 3.a | 1780"* on the title page, and every one carries the note
**"Vgl. auch die Stimmensätze KHM 577 und KHM 578"** — *compare also the part-sets KHM 577
and KHM 578*. RISM is pointing from the scores to the parts.

So these are the same six works as `KHM 577`, but in **score**, one volume per quartet. Not a
second copy of the part-set — a different form of the text, which for a source study is a
different witness, not a duplicate.

### `KHM 577`, `578` — Op. 32 **part-sets**

Both read *"Berliner Stimmensatz der Quartette op. 32"*, 4 parts each. We hold `KHM 577`
(PPN84753183X, 161 images). `KHM 578` is a second part-set, not digitized.

| shelfmark | what it is | Gérard | RISM | digitized |
|---|---|---|---|---|
| KHM 569 | Op. 22 part-set | — | [463056900](https://rism.online/sources/463056900) | no |
| KHM 570 | Op. 22 part-set | 183 | [463057000](https://rism.online/sources/463057000) | no |
| KHM 571–576 | Op. 32 **scores**, 1 quartet each | 201–206 | [463057100](https://rism.online/sources/463057100)–[463057600](https://rism.online/sources/463057600) | no |
| **KHM 577** | Op. 32 **part-set** | **201–206** | [463057700](https://rism.online/sources/463057700) | **yes — held** |
| KHM 578 | Op. 32 part-set | 201 | [463057800](https://rism.online/sources/463057800) | no |
| KHM 590 | Quartettino | 216 | [463059000](https://rism.online/sources/463059000) | no |
| KHM 592 | Quartettino | 217 | [463059200](https://rism.online/sources/463059200) | no |

## What Op. 32 actually looks like on disk

Worth stating plainly, because it bears on whether `KHM 571`–`576` are worth ordering.

**Every Op. 32 item held is a print, except one.**

| folder | siglum | shelfmark | kind |
|---|---|---|---|
| `G201-206/463057700_D-B` | D-B | `KHM 577` | **manuscript**, 161 images |
| `G201-206/990005880_F-Pc` | F-Pc | `AC E4-133` | print |
| `G201-206/990005880_US-CAe` | US-CAe | `Mus 631.1.329.5` | print |
| `G201-206/990005883_D-B` | D-B | `DMS 51778` | print |
| `G201-206/1001263271_E-Mn` | E-Mn | `Mp/2393\|2` | print |
| `G201-206/bne-e4e2d08c-6b3` | E-Mn | `Mp/2393\|1` | print, Artaria |
| `G201-206/bne-495569cd-001` | E-Mn | `Mp/2393\|2` | print, duplicate of `1001263271_E-Mn` |

The Paris item is `AC E4-133` on Gallica, and it is RISM
[990005880](https://rism.online/sources/990005880) — the **Artaria print**, not a manuscript.
The Paris *manuscript* in this collection is `RES-507 (2)`, F-Po, and that is **Op. 33**
(G 207–212), a different set.

So `KHM 577` is the **only manuscript witness to Op. 32 we hold**, and it is a *part-set*.
`KHM 571`–`576` are the same six works **in score** — not another copy of the parts, but the
other form of the text, which RISM's own notes cross-reference in that direction. We hold no
score of Op. 32 at all.

## If you want the eleven

They would have to be ordered from the Musikabteilung. `KHM 571`–`576` as a block is the
coherent ask: Op. 32 complete in score, one quartet per volume, against the part-set we
already hold.

## A note on how `KHM 577` is filed

RISM gives 463057700 no GerB number, so the harvester files it under `unidentified/` every
time. Editing the folder's `metadata.json` does not survive — `relocate()` rebuilds the
folder name from RISM on the next run and moves it straight back. The six numbers therefore
live in `corrections.json` under `463057700`, which is what makes the placement stick.
