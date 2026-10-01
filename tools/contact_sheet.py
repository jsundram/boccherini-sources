# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Render an item so its structure can be read at a glance.

    uv run tools/contact_sheet.py digitizations/G245-247/990005886_D-B_livr2
    uv run tools/contact_sheet.py --full <dir>        # whole pages, not just the head
    uv run tools/contact_sheet.py --g 242             # every folder for a Gérard number

Writes a PNG next to nothing -- into `sheets/` -- and prints the path.

**Head strips are the useful default.** A printed part-book announces itself at the top of
the page: `IV. QUATUOR`, `VIOLINO I°`, `Andante Sostenuto`. Stacking the top eighth of every
page puts every one of those announcements in a single column, so the structure of a
70-page PDF -- which quartets, in what order, in how many part-books -- can be read in one
look. That is how Op. 58 was settled: livraison 2 showed IV at p5, V at p11, VI at p17, and
Violino Secondo restarting at IV on p23, which proved each livraison holds three quartets
and not six.

This does not replace looking. It makes looking cheap enough to actually do.
"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

DIG = Path('digitizations')
OUT = Path('sheets')


def pages(d, limit):
    """(label, path) for up to `limit` pages, from the PDFs or the images."""
    import itertools
    jp = sorted(d.glob('*.jpg'))
    if jp:
        return [(p.stem, p) for p in jp[:limit]], None
    pdfs = [p for p in sorted(d.glob('*.pdf')) if 'cover' not in p.stem.lower()]
    if not pdfs: return [], None
    td = tempfile.mkdtemp()
    out = []
    for pdf in pdfs:
        n = limit - len(out)
        if n <= 0: break
        subprocess.run(['pdftoppm', '-f', '1', '-l', str(n), '-r', '40', '-jpeg',
                        str(pdf), f'{td}/{pdf.stem}'], capture_output=True, timeout=900)
        out += [(f'{pdf.stem[-14:]}:{p.name.split("-")[-1].split(".")[0]}', p)
                for p in sorted(Path(td).glob(f'{pdf.stem}-*.jpg'))]
    return out[:limit], td


def sheet(d, full=False, limit=80):
    from PIL import Image, ImageDraw
    ps, td = pages(d, limit)
    if not ps:
        print(f'  {d}: nothing to render', file=sys.stderr); return None
    tiles = []
    for lab, f in ps:
        im = Image.open(f).convert('RGB')
        if not full:
            w, h = im.size
            im = im.crop((0, 0, w, int(h * 0.13)))
        im.thumbnail((620, 620) if not full else (230, 230))
        tiles.append((lab, im))
    if full:
        cols = 8
        cw = max(i.width for _, i in tiles) + 8
        ch = max(i.height for _, i in tiles) + 16
        rows = (len(tiles) + cols - 1) // cols
        sh = Image.new('RGB', (cw * cols, ch * rows), 'white')
        dr = ImageDraw.Draw(sh)
        for k, (lab, i) in enumerate(tiles):
            x, y = (k % cols) * cw + 4, (k // cols) * ch + 13
            sh.paste(i, (x, y)); dr.text((x, y - 11), lab[-12:], fill='#a00')
    else:
        W = max(i.width for _, i in tiles) + 62
        H = sum(i.height + 3 for _, i in tiles) + 6
        sh = Image.new('RGB', (W, H), 'white')
        dr = ImageDraw.Draw(sh)
        y = 3
        for lab, i in tiles:
            dr.text((2, y + 3), lab[-14:], fill='#a00')
            sh.paste(i, (58, y)); y += i.height + 3
    OUT.mkdir(exist_ok=True)
    out = OUT / f"{d.name}{'-full' if full else ''}.png"
    sh.save(out)
    print(out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('dirs', nargs='*', type=Path)
    ap.add_argument('--g', help='every folder filed under this Gérard number')
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--limit', type=int, default=80)
    a = ap.parse_args()
    targets = list(a.dirs)
    if a.g:
        for p in sorted(DIG.rglob('metadata.json')):
            m = json.loads(p.read_text())
            gs = {str(x) for x in (m.get('gerard_numbers') or [])} | {str(m.get('gerard'))}
            if a.g in gs: targets.append(p.parent)
    for d in targets:
        sheet(d, a.full, a.limit)


if __name__ == '__main__':
    main()
