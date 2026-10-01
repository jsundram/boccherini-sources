# Page images, collated PDFs, and where the JPEGs went

**The scans now live as one PDF per item.** The 3,833 loose page images they were built from
are in `~/.Trash/boccherini-page-images-2026-09-28/`, not deleted — recoverable by dragging
the folder back.

This is safe because it was proven rather than assumed, and because the harvester was taught
about it first. Both parts matter; skipping either loses data.

## Why the images were collapsed

A IIIF manifest serves one file per page, so 88 folders held runs of `001.jpg`, `002.jpg`…
That is the right archival form and the wrong form for reading or sending to anybody. The
archive was 9.5 GB of images; collating added 8 GB of PDFs on top, and holding both was
the actual waste.

## Why it is lossless

`img2pdf` embeds JPEG data with no re-encoding — the bytes in the PDF are the bytes that
were on disk. `verify_pdfs.py` extracts every image back out with `pdfimages -j` and
compares MD5s:

> **88 folders, 3,833 pages, 0 failures.**

Per-page checksums are in `../pdf-verification.jsonl`, so the claim stays checkable. To get
an original back:

```sh
pdfimages -j -p digitizations/G183/463056300_D-B/463056300_D-B.pdf out
```

## What the filenames knew

Most page names carried nothing but order, which a PDF keeps. Three folders were different,
and `preserve_page_labels.py` moved what they encoded into each sidecar's `page_index`
block before anything moved:

| folder | filenames | now recorded as |
|---|---|---|
| `550503024_CZ-Pu` | `01-cover`, `03-title`, `04-vc`, `09-v1`, `13-v2`, `17-va` | `opens: cover / title / violoncello / violin 1 …` — the hand-marked part boundaries |
| `650004089_A-ST` | `..._MusMs577_vl1_2vSm.jpg` | `shelfmark: Mus.ms. 577`, `part: violin 1`, `folio: 2v`, `opus: Op. 8 no. 2` |
| `650004090_A-ST` | `..._MusMs576_vlc1r.jpg` | the same, for `Mus.ms. 576` |

Those Muscat attachment names were the only record of which part and folio each image
showed. `make_part_pdfs.py` reads the CZ-Pu suffixes and had already produced its part
PDFs, which is why that folder could be collapsed without losing the split.

## The trap this would otherwise have set

`rism_digitizations.py` resumed per file:

```python
f = d / f'{i:03d}.jpg'
if f.exists() and f.stat().st_size: continue
```

Delete `001.jpg` and the next `--download` refetches it — all 8 GB, over links that in
several cases no longer resolve. **This actually happened** during the work: a harvest run
before both loops were guarded pulled 99 images back down across four folders.

There are **two** page loops — the RISM-linked path and the hand-found path — and both now
call `pdf_is_complete(d, n)`, which skips the item when `<folder>.pdf` already holds at
least as many pages as the manifest lists. Guarding one and not the other is exactly the
bug that bit.

## Order of operations, if this is ever done again

1. `uv run tools/collate_pdfs.py` — write the PDFs
2. `uv run tools/verify_pdfs.py --report` — prove every page round-trips
3. `uv run tools/preserve_page_labels.py` — move filename facts into the sidecars
4. confirm both loops in `rism_digitizations.py` call `pdf_is_complete`
5. `uv run tools/oneoff/trash_collated_jpegs.py --dry-run`, then for real

`trash_collated_jpegs.py` moves a file only when its folder passed verification, the
manifest lists that exact filename, and the file's MD5 still matches what was recorded.
Anything else is left alone.
