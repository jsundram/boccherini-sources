# /// script
# requires-python = ">=3.11"
# dependencies = ["img2pdf"]
# ///
"""Collate each run of page images into one PDF, so an item can be opened and shared.

    uv run tools/collate_pdfs.py              # every folder that needs one
    uv run tools/collate_pdfs.py --dry-run    # say what would be written
    uv run tools/collate_pdfs.py --force      # rebuild even if the PDF is current
    uv run tools/collate_pdfs.py digitizations/G183/463056300_D-B

88 folders hold their scans as loose JPEGs -- one file per page, because that is what a
IIIF manifest serves. That is the right archival form and the wrong form for reading or
sending to anybody, so each gets a sibling PDF named after the folder.

`img2pdf` embeds the original JPEG bytes without re-encoding, so the PDF is the same
pixels at the same size, not a lossy copy of a lossy copy. Nothing is deleted: the images
remain the source of truth and the PDF is derived, regenerated whenever the images change.

Related but different: `make_part_pdfs.py` splits a hand-numbered run into one PDF per
instrumental part, using suffixes in the filenames. This just collates what is there.
"""
DPI = 300          # every page box follows its pixels at this scale

import argparse
import sys
from pathlib import Path

DIG = Path('digitizations')


def pages(d):
    return sorted(d.glob('*.jpg'))


def target(d):
    return d / f'{d.name}.pdf'


def stale(d):
    """A PDF is current when it is newer than every image it was made from."""
    t = target(d)
    if not t.exists():
        return True
    newest = max(p.stat().st_mtime for p in pages(d))
    return t.stat().st_mtime < newest


def collate(d, force=False, dry=False):
    ps = pages(d)
    if not ps:
        return None
    t = target(d)
    if not force and not stale(d):
        return ('current', t, len(ps))
    if dry:
        return ('would write', t, len(ps))
    import img2pdf
    # One page box per image sounds right and is not: img2pdf sizes each page from that
    # JPEG's own embedded DPI, and Berlin's scans mix 96 and 300 dpi in their JFIF headers
    # for images of identical pixel size. That put one page in twelve on a box 3.1x larger
    # than its neighbours -- same pixels, so a viewer upscales it and the page looks blurred
    # beside the rest. Fixing the dpi makes the box follow the pixels, which is what a page
    # box is for. 320 pages across 38 Berlin files were built this way before this was found.
    layout = img2pdf.get_fixed_dpi_layout_fun((DPI, DPI))
    data = img2pdf.convert([str(p) for p in ps], layout_fun=layout)
    t.write_bytes(data)
    return ('wrote', t, len(ps))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('dirs', nargs='*', type=Path)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    if a.dirs:
        targets = a.dirs
    else:
        targets = sorted({p.parent for p in DIG.rglob('*.jpg')})
    wrote = skipped = 0
    total = 0
    for d in targets:
        r = collate(d, a.force, a.dry_run)
        if not r:
            continue
        what, t, n = r
        if what == 'current':
            skipped += 1
            continue
        wrote += 1
        total += t.stat().st_size if t.exists() else 0
        print(f'  {what:11} {t.relative_to(DIG)}  ({n} pages)', file=sys.stderr)
    print(f'{wrote} written, {skipped} already current'
          + (f', {total/1e9:.2f} GB' if total else ''), file=sys.stderr)


if __name__ == '__main__':
    main()
