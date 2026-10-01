# TODO

Open work, roughly by value. Counts are not written here — they drift, and `boc check` fails
when a document disagrees with the data. Run the command instead.

```sh
uv run boc.py status     # where the archive stands
uv run boc.py todo       # the items a person has to settle
```

---

## 1. Is F-Po `RES-507` Boccherini's hand, or Picquot's?

**Four items on disk hang on this.** RISM types all six `RES-507` sources *Autograph
manuscript*, dated 1794 — and on `RES-507 (14)` it also names **Louis Picquot as scribe**,
a man born in 1804. It cannot be both.

We hold `(14)`, `(16)`, `(17)`, `(18)` as `medium: autograph` on RISM's word, at tier D
(*asserted, never checked*). The pages would answer it: Boccherini's hand does not look like
Picquot's.

```sh
uv run boc.py look digitizations/G228/btv1b52502357c     # RES-507 (14), G 228
uv run boc.py show digitizations/G228/btv1b52502357c
```

Background and the full contradiction: `digitizations/PICQUOT-COPIES.md`.
If the set is Picquot's copies, four labels and the archive's autograph count change.

## 2. Two questions about F-Pn `Vmb MS-153`

Held as `G184_185_186_188/btv1b52514840q` — a Gallica volume covering G 184, 185, 186 and 188, the same
Op. 22 set the Madrid copies belong to.

**RISM files two records under G 188 there** — [840022735](https://rism.online/sources/840022735)
and [840022737](https://rism.online/sources/840022737). Either a duplication or two distinct
movements; unresolved.

**It declares four parts but holds three separated part PDFs** — violin 1, violin 2 and
viola. The cello is absent from the split, though it should be inside the 92 MB whole-volume
file. That is why it sits in the review queue as `parts-short`.

Its internal numbering also disagrees with the opus order — *Quartetto I* is G 186, *II* is
G 184, *III* is G 188, *IV* is G 185 — where the Madrid copies number them as the opus does.
Worth recording properly if you collate the two.

## 3. The five Madrid copies are unknown to RISM

`E-Mc` (Real Conservatorio Superior de Música de Madrid) appears **nowhere** in RISM's
quartet corpus; its only Madrid sigla are E-Mn and E-Mp. The five copies now held under
G 183-186 and G 188 are Madrid court copies of 1782 from originals of 1775, published by the
library itself and catalogued by Gosálvez and Labrador (2004).

They sit at tier D because no RISM record exists to corroborate them. Reporting them to RISM
would be a contribution rather than a correction. Quartet V (G 187) was already missing from
the 19th-century catalogues, so the set is five of six.

## 4. Work the review queue

The only substantial job no tool can finish.

```sh
uv run boc.py todo       # ranked, with the reason each was flagged
uv run boc.py review     # build review.html, decide in the browser, export verdicts
uv run boc.py apply <verdicts.json>
```

Most of the queue is BnF material. The manuscripts are outside OCR entirely, so those need
eyes on a contact sheet (`uv run boc.py look <folder>`).

## 5. Re-read RISM

`harvest` has not actually run since before the `Vma ms 1067` intake — it was vouched, not
run, because only a docstring had changed. It is the stage that notices new digitizations
appearing at libraries whose holdings we do not have.

```sh
uv run boc.py harvest    # slow, needs network
```

## 6. Chase the two missing Op. 48 autographs

`RES-507 (13)` (G 226) and `(15)` (G 227) complete the autograph set we otherwise hold whole.
RISM's `856` link for both points at the BnF **catalogue**, not at Gallica, which is why the
harvester never fetched them — a catalogue record is not a scan.

- [840013701](https://rism.online/sources/840013701) → `catalogue.bnf.fr/ark:/12148/cb39607518s`
- [840013709](https://rism.online/sources/840013709) → `catalogue.bnf.fr/ark:/12148/cb39607526d`

Check whether Gallica holds images behind either.

**This is a class, not two items.** `resolve()` in `tools/rism_digitizations.py` has one BnF
resolver and it matches `gallica\.bnf\.fr`. A `catalogue.bnf.fr` link resolves to `None` and
the record is skipped as unresolvable, so the harvester cannot tell *no scan exists* from
*the link points at a catalogue record*. Every F-Pn `Vma ms 1067` record has the same shape.
A resolver that followed a catalogue ark through to a Gallica ark, where one exists, would
close the class:

```sh
grep -n "r_gallica\|RESOLVERS" tools/rism_digitizations.py
```

## 7. Write to Mulhouse about `mn.4862`

A book cites `F-MH mn.4862` as 19th-century MS copies of Op. 48. RISM records ten Boccherini
holdings at F-MH, **all prints, none Op. 48** — but the shelfmark series has a vacant slot at
exactly `4862,1`, and five of the ten F-MH records give no shelfmark at all. The book is
verbatim-accurate everywhere else it can be checked.

Reasoning: `digitizations/PICQUOT-COPIES.md`. Write the letter as a new `*-REQUEST.md`,
following `digitizations/STAMS-REQUEST.md` for shape.

## 8. Send the letters already drafted

`digitizations/STAMS-REQUEST.md`, `MUENSTER-REQUEST.md`, `UDK-REQUEST.md` — German and
English, with prices and shelfmarks worked out. Unsent.

`MUENSTER` is the one to pay for: `SANT Hs 531` is the only remaining autograph candidate
genuinely contemporary with Boccherini, and RISM says its viola and bass parts are *not*
autograph, which implies the violin parts may be.

---

## Upstream, not here

**`digitizations/UNLINKED-HOLDINGS.md` still prints pre-relocation paths.** It is generated
by `harvest`, which has not run since the 36 Gallica finds were filed under their Gérard
numbers, so it names `found/BnF/...` for items that have moved. Running `boc harvest` fixes
it; nothing else reads those strings.

**`bnf/page-index.md` has 131 broken photo links.** Moving the BnF output into
`_RAW/output/bnf/` on 2026-09-30 left its relative links pointing at
`../_Melissa - BNF Scans - RAW/…`, which resolved from `output/` and now need `../../`.
Verified: 0 of 131 resolve from the new location, 131 of 131 would from the old. The fix
belongs in whatever generates that file. The archive's own copies are unaffected — they are
used for the page-to-photograph mapping, not as clickable links.

## Standing risks, not tasks

**Melissa's raw photographs are unprotected.** The BnF originals — 747 MB in
`boccherini-quartet-data/manuscripts/_RAW/_Melissa - BNF Scans - RAW/` — are what the six
`Vma ms 1067` PDFs derive from, and they sit outside the archive where `boc protect` cannot
reach them. Either copy them in and declare them, or accept the gap knowingly.

**Dropbox is sync, not backup.** Everything declared in `originals.jsonl` lives only there.
The checksums will tell you a file changed; they cannot undo it. A copy that is not Dropbox
is the missing piece.

```sh
uv run boc.py protect          # verify every irreplaceable file, byte for byte
uv run boc.py protect --list
```

## Deferred decisions

**The two BNE skip folders.** `unidentified/bne-9e94ee06-c0c` and `bne-a7335745-837` hold no
scan but do hold a decision not to download one (Pleyel oeuvre 39, 2e and 3e livraison:
better copies held, BNE's scan poor). `tools/parse_portal_results.py` reads `skipped: true`
off those folders to keep them off the worklist, so removing them puts both back on it. To
remove them, the decision needs somewhere else to live first.

**Citations need a siglum.** `uv run boc.py find "F-Pn Vma ms 1067"` resolves; the same query
without `F-Pn` returns nothing. Fine for real citations, a trap for bare shelfmarks pasted
from notes.
