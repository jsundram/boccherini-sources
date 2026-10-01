# PDF verification

Every one of the **99 page images** in the 4 collated PDFs was extracted back out with `pdfimages -j` and compared by MD5 against the file on disk.

**4 of 4 folders passed.**

`img2pdf` embeds JPEG data without re-encoding, so this is expected; it is recorded because the originals are only safe to move once it is proven rather than assumed. Per-page checksums are in `../pdf-verification.jsonl`.
