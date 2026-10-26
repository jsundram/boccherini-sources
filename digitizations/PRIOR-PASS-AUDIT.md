# Audit of the earlier download passes

Source: `boccherini-quartet-data/manuscripts` — 61 files, 1.9 GB. **Nothing was moved.**
Only the genuinely new material was copied in.

Files marked *Andrew* or *Melissa* are friends' photographs of the French manuscripts and
were excluded from the audit, as instructed. That leaves **47 PDFs**.

## The answer in one table

| provenance | files | already had | new |
|---|---:|---:|---:|
| D-B, Staatsbibliothek zu Berlin (`KHM 563–603`) | 25 | **25** | 0 |
| D-Eu, Eichstätt (`Esl VIII 351–357`) | 6 | **6** | 0 |
| F-Pn / F-Po via Gallica | 14 | 11 | **3** |
| US-Wc, Library of Congress | 2 | 0 | **2** |

**Five files were new. Forty-two we already had.**

But the real return was not files — see *What the audit was actually worth*, below.

---

## How each was matched

Most of these PDFs carry a text layer with full provenance, so matching was on
identifiers rather than guesswork.

**Berlin** — every file embeds its PURL, e.g.
`resolver.staatsbibliothek-berlin.de/SBB0001C5D100000000`, which is exactly what our
folders store. All 25 matched, and **every one matched page-for-page**: the PDF always has
one page more than our folder, because SBB prepends a metadata sheet the IIIF manifest does
not include.

```
KHM 563     34p    33 on disk    G183/463056300_D-B
KHM 596     10p     9 on disk    G220/463059600_D-B   (the Op. 44 no. 1 autograph score)
KHM 603     26p    25 on disk    G227/1001015845_D-B
```

**Eichstätt** — matched on shelfmark `Esl VIII 351`–`357`, all six already filed under
G 159–164. Note the sixth is `357`, not `356`.

**Gallica** — no ark in the text, so matched on Gallica's own title string and page count
(Gallica PDFs add two front pages). Eleven of fourteen matched immediately. One,
`RES-507 (17)`, failed only because Gallica has since reworded its title from
*"(manuscrit autographe)"* to *"(manuscrit **en partie** autographe)"* — same item,
20 canvases + 2.

---

## What was new

### 1. Three part-books of F-Pn `Vm.b Ms 153` — a real gap, now filled

Our folder `found/BnF/btv1b52514840q` held 42 images. The cover reads **Violoncello**.
The earlier pass has three more part-books from the same shelfmark — the V1 cover carries
the same `MVSIQVE / Vm.b Ms / 153(1-5)` stamp and the Gallica footer.

Gallica **cannot supply these today**. Its ark has 42 canvases running `plat sup.` to
`plat inf.`, and the record itself says *"4 parties … Nombre total de vues : 42"* — the
catalogue describes four parts and digitizes one. Searching by title and by shelfmark
returns that single ark and nothing else.

Copied into the same folder, since they are one physical shelfmark:

| part | file | pages |
|---|---|---|
| Violino I | `Vmb-Ms-153.violin1.pdf` | 42 |
| Violino II | `Vmb-Ms-153.violin2.pdf` | 38 |
| Viola | `Vmb-Ms-153.viola.pdf` | 40 |
| Violoncello | `001.jpg … 042.jpg` | 42 |

The three PDFs are 1024×1536 — lower resolution than the cello part's full-res images.
That is what the earlier pass captured, and it is no longer improvable from Gallica.

### 2. Library of Congress, Op. 64 — `G248-249/US-Wc_M452-A2-B68/`

*1804 // Opera 64. // Quartetto Primo // Violino Primo // Boccherini.* 34 pages.

Boccherini's last quartets, dated the year before his death. RISM does not catalogue this
copy; it lists the two works at DK-Km (`R454`/`R455`), Harvard (`fMS Mus 6`) and F-Pn
(`Vma ms 1067 (5)`/`(6)`), and digitizes none of them.

> **Corrected 2026-10-26.** This said *"the only copy of G 248–249 in the project"*. It was
> not: Melissa's BnF photographs of `Vma ms 1067` carry both, at `G248/840022759_F-Pn` and
> `G249/840022760_F-Pn`. They were invisible here because this audit excluded friends'
> photographs, and in `CONCORDANCE.md` because this folder was linked as a `copy` of all
> six RISM records, so every one of them showed the LoC scan as the copy held. It is now
> linked as `work`.

### 3. Library of Congress, Op. 54 — `G250-255/US-Wc_M452-A2-B68-op54/`

*Opera 54 … 1796 … Tre Quartetti Per due Violini, Viola e Basso … Violino Primo.* 85 pages.

Two things are unresolved and the folder says so: the title page reads **Tre Quartetti**
where the prior filename says *Numbers 1-6*, and **no GerB number above 249 appears
anywhere in the harvested RISM records**, so this set sits outside the catalogue this
project indexes.

---

## What the audit was actually worth

> **Update, 2026-09-28.** These eleven were the first identifications; a later pass
> identified **30** folders in total and left none outstanding. See
> [`TO-IDENTIFY.md`](TO-IDENTIFY.md) and the *identification pass* section of
> `../STATUS.md`. The eleven below are still the ones this audit supplied.

Not the five files — the **eleven identifications**.

Every Gallica folder in `found/BnF` had `gerard: null`. RISM assigns no GerB number to
these sources, so nothing in the pipeline could supply one. The earlier pass had already
worked them out, and its filenames map cleanly onto the arks:

| ark | siglum | shelfmark | Gérard | opus | autograph |
|---|---|---|---|---|---|
| `btv1b52514840q` | F-Pn | `Vm.b Ms 153` | 184, 185, 186, 188 | Op. 22 nos. 4, 2, 6, 3 | |
| `btv1b10537292r` | F-Pn | `MS-1292` | 189–194 | Op. 24 complete | **yes** |
| `btv1b52502470f` | F-Po | `RES-507 (2)` | 207–212 | Op. 33 complete | **yes** |
| `btv1b108677212` | F-Pn | `D-11157` | 216 | Op. 42 no. 1 | |
| `btv1b10867724d` | F-Pn | `D-11158` | 217 | Op. 42 no. 2 | |
| `btv1b525026043` | F-Po | `RES-507 (10)` | 223 | Op. 44 no. 4, *La Tiranna* | **yes** |
| `btv1b525024781` | F-Po | `RES-507 (11)` | 224 | Op. 44 no. 5 | **yes** |
| `btv1b52502357c` | F-Po | `RES-507 (14)` | 228 | Op. 48 no. 3 | **yes** |
| `btv1b52502403w` | F-Po | `RES-507 (16)` | 229 | Op. 48 no. 4 | **yes** |
| `btv1b52502472b` | F-Po | `RES-507 (17)` | 230 | Op. 48 no. 5 | part autograph |
| `btv1b525023598` | F-Po | `RES-507 (18)` | 231 | Op. 48 no. 6 | **yes** |

Recorded in each folder's `metadata.json` as `gerard_established_by`, attributed to the
earlier pass rather than to RISM.

That includes **seven of the F-Po autographs**, which until now were the unnumbered rows at
the top of `UNLINKED-HOLDINGS.md`. They are the manuscripts Boccherini dated by month —
*Mese di Giugno 1794*, *Mese di Ottobre 1792* — and they now carry their Gérard numbers.

## Still worth knowing

The earlier pass covered Berlin and Eichstätt **completely and exactly**. Every Berlin
shelfmark in it, `KHM 563` through `KHM 603`, is already held at full resolution. There is
nothing to re-download there, and the pending Berlin search for `KHM 569–578`, `590` and
`592` is for shelfmarks the earlier pass never had either.
