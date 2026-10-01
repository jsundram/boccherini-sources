# /// script
# requires-python = ">=3.11"
# dependencies = ["img2pdf"]
# ///
"""Rebuild PDFs whose page boxes disagree with their pixels.

Berlin's JPEGs carry 96 dpi in the JFIF header on some pages and 300 on others, for images
of the same pixel size. `img2pdf` sizes each page from that header, so one page in twelve
landed on a box 3.1x larger than its neighbours -- the same pixels, stretched, which a
viewer upscales and renders soft beside the rest. No pixels were ever lost: the IIIF
`info.json` for every affected page reports exactly the size we already hold.

This rebuilds the affected files at a uniform dpi. The JPEG bytes are lifted out of the PDF
with `pdfimages -j`, which returns the original DCT streams, and written back unchanged, so
nothing is re-encoded and nothing is re-downloaded. Every image is compared by sha256
before and after; a file that does not match is left exactly as it was.

    uv run tools/oneoff/renormalize_page_boxes.py --dry-run
    uv run tools/oneoff/renormalize_page_boxes.py

The cause is fixed in `collate_pdfs.py`, so this is a one-off for files built before that.
"""
import argparse, hashlib, shutil, subprocess, sys, tempfile
from datetime import date
from pathlib import Path

DIG = Path('digitizations')
DPI = 300


def ppi_of(pdf):
    """[(page, x-ppi)] for every embedded image."""
    out = []
    r = subprocess.run(['pdfimages', '-list', str(pdf)], capture_output=True, text=True)
    for line in r.stdout.splitlines()[2:]:
        f = line.split()
        if len(f) > 6 and f[0].isdigit():
            try:
                out.append((int(f[0]), int(f[-4])))
            except ValueError:
                pass
    return out


def affected(pdf):
    p = ppi_of(pdf)
    got = {x for _, x in p}
    return len(got) > 1 and 96 in got and 300 in got


def n_pages(pdf):
    r = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True)
    for l in r.stdout.splitlines():
        if l.startswith('Pages:'):
            return int(l.split(':')[1])
    return 0


def digests(d):
    return [hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.glob('*.jpg'))]


def rebuild(pdf, trash, dry=False):
    import img2pdf
    pages = n_pages(pdf)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        subprocess.run(['pdfimages', '-j', str(pdf), str(td / 'p')],
                       capture_output=True, check=False)
        jpgs = sorted(td.glob('*.jpg'))
        other = [f for f in td.iterdir() if f.suffix != '.jpg']
        if other:
            return 'skip', f'{len(other)} non-JPEG image(s); not a pure JPEG document'
        if len(jpgs) != pages:
            return 'skip', f'{len(jpgs)} image(s) for {pages} page(s); not one image per page'
        before = digests(td)
        if dry:
            return 'would rebuild', f'{pages} pages'
        layout = img2pdf.get_fixed_dpi_layout_fun((DPI, DPI))
        data = img2pdf.convert([str(f) for f in jpgs], layout_fun=layout)
        new = td / 'rebuilt.pdf'
        new.write_bytes(data)
        # prove the bytes survived
        chk = td / 'chk'
        chk.mkdir()
        subprocess.run(['pdfimages', '-j', str(new), str(chk / 'p')],
                       capture_output=True, check=False)
        after = digests(chk)
        if after != before:
            return 'FAILED', 'images changed in the rebuild; original left untouched'
        if {x for _, x in ppi_of(new)} != {DPI}:
            return 'FAILED', 'rebuilt file still has mixed dpi; original left untouched'
        trash.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdf), str(trash / f'{pdf.parent.name}--{pdf.name}'))
        shutil.move(str(new), str(pdf))
        return 'rebuilt', f'{pages} pages, all {DPI} dpi'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    trash = Path.home() / '.Trash' / f'boccherini-mixed-dpi-originals-{date.today()}'
    todo = [p for p in sorted(DIG.rglob('*.pdf')) if affected(p)]
    print(f'{len(todo)} file(s) with mixed 96/300 dpi\n', file=sys.stderr)
    done = skipped = failed = 0
    for p in todo:
        state, why = rebuild(p, trash, a.dry_run)
        print(f'  {state:13} {p.relative_to(DIG)}  — {why}', file=sys.stderr)
        done += state in ('rebuilt', 'would rebuild')
        skipped += state == 'skip'
        failed += state == 'FAILED'
    print(f'\n{done} rebuilt, {skipped} skipped, {failed} failed', file=sys.stderr)
    if done and not a.dry_run:
        print(f'originals in {trash}', file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
