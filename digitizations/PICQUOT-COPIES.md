# Louis Picquot (1804–1870), and a dating contradiction in RISM

Established 2026-09-30, prompted by a book citing *"MS Copies (separate parts: 19th
century)"* for Op. 48 and listing `F-MH mn.4862` alongside `D-11169`, *"in the hand of
Picquot, with a note: beau"*.

Reproduce with:

```sh
grep -ril picquot .rism-cache | wc -l          # sources naming him
uv run boc.py find "F-Pn D-11169"              # what we hold for it
```

## The citation checks out verbatim

RISM's own note on [840013720](https://rism.online/sources/840013720) (`F-Pn D-11169`, G 228):

> *Autres mentions, de la main de L. Picquot à la p. de t. : "Ouvrage inédit", "beau", "Op. 48"*

`D-11172` carries *"très beau"*. So the book is reading RISM's notes, or the same title
pages, and is reliable on this set.

## Picquot was Boccherini's first biographer, and owned the autographs

RISM's authority record dates him **1804–1870** and gives him two relator codes across the
quartet corpus: `fmo` (former owner) and `scr` (scribe). He owned the F-Po `RES-507`
autographs — Boccherini's own manuscripts — and the F-Pn `D-111xx` series is his copies,
which is exactly what the book's *"MS Copies (separate parts: 19th century)"* describes.

## The contradiction

RISM names Picquot as **scribe** on 18 quartet sources. **Sixteen are dated before 1810** —
that is, before or barely after his birth in 1804:

| dated | n | verdict |
|---|---|---|
| `[Entre 1790 et 1810]`, `[Entre 1792 et 1810]`, `[Entre 1794 et 1810]`, `1794` | 16 | **impossible** — he was not born until 1804 |
| `[Entre 1820 et 1850]` | 2 | plausible (`D-11159`, `D-11161`) |

Either the scribe attribution or the date range is wrong on those sixteen. The book's
*"19th century"* is the reading that survives; RISM's `[Entre 1794 et 1810]` does not.
The two records RISM dates 1820–1850 show what the rest should probably look like.

## One of the sixteen is a label we depend on

[840013721](https://rism.online/sources/840013721) — `F-Po RES-507 (14)`, G 228, which this
archive **holds** as `G228/btv1b52502357c` — is typed *Autograph manuscript*, dated
**1794**, and names **Picquot as scribe**. It cannot be both Boccherini's autograph and
written by a man born in 1804.

We label it `medium: autograph` on RISM's word, and it sits at tier D, *asserted, never
checked*, along with `RES-507 (16)`, `(17)` and `(18)`. Whether the whole `RES-507` set is
autograph or Picquot's copy is a question about four items we have on disk, and the pages
would answer it — a hand that is Boccherini's does not look like a hand that is Picquot's.

## Why `F-MH mn.4862` is worth chasing

RISM records ten Boccherini quartet holdings at F-MH (Bibliothèque municipale, Mulhouse),
**every one a print, none of them Op. 48**. The two `MN 4862` shelfmarks it does list hold
Op. 24 and Op. 26. But the Mulhouse series runs `MN 4861,1`–`4861,8` and `4862,2`–`4862,3`
with **`4861,4` and `4862,1` absent from RISM entirely**, and five of the ten F-MH records
give no shelfmark at all.

So an uncatalogued Picquot-tradition copy set of Op. 48 at `mn.4862` is consistent with
everything here: the book is verbatim-accurate where it can be checked, RISM is
demonstrably incomplete at this library, and there is a vacant slot exactly where the
citation points. Worth a letter to Mulhouse.
