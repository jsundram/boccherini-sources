# tools/oneoff/

Migrations that have already run. Kept because how a thing was done is part of the record —
not because they should be run again.

| | what it did | re-running it |
|---|---|---|
| `trash_collated_jpegs.py` | moved 3,833 page images to `~/.Trash` once `verify_pdfs.py` proved every byte survived inside the collated PDFs | **destructive.** It moves files out of the archive. It refuses anything not verified, but do not reach for it casually |
| `survey_portals.py` | produced `PORTAL-SURVEY.md`, the per-library verdict on whether a portal can be searched by a script | harmless, but the survey is done |
| `make_part_pdfs.py` | split a hand-numbered image run into one PDF per instrumental part, reading the `-vc` / `-v1` suffixes | still useful, but only when such a download arrives |

The page images these refer to are described in `../../digitizations/PAGE-IMAGES-AND-PDFS.md`.

## `renormalize_page_boxes.py`

Ran 2026-09-30 over 38 Berlin files, 320 pages. Their JPEGs carry 96 dpi in the JFIF
header on some pages and 300 on others for images of identical pixel size, and `img2pdf`
sized each page box from that header — so one page in twelve sat on a box 3.1x too large
and a viewer upscaled it. No pixels were ever lost; the IIIF `info.json` for every
affected page reports exactly the size already held. The JPEG bytes were lifted out with
`pdfimages -j`, written back unchanged at a uniform 300 dpi, and compared by sha256
before and after. Originals in `~/.Trash/boccherini-mixed-dpi-originals-2026-09-30/`.

The cause is fixed in `collate_pdfs.py`, so this should never need running again.
