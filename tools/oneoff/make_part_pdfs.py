# /// script
# requires-python = ">=3.11"
# dependencies = ["img2pdf"]
# ///
"""Turn a hand-downloaded run of page images into a whole PDF and one PDF per part.

    uv run tools/oneoff/make_part_pdfs.py                         # every item that needs it
    uv run tools/oneoff/make_part_pdfs.py digitizations/G162/550503024_CZ-Pu
    uv run tools/oneoff/make_part_pdfs.py --force <dir>           # rebuild existing PDFs

Some libraries only serve one page at a time, so a manual download arrives as a pile of
images rather than the single PDF `MANUAL-DOWNLOADS.md` asks for. Name them in page order
and mark where each part begins:

    01-cover.jpg  02.jpg  03-title.jpg  04-vc.jpg  05.jpg … 09-v1.jpg … 13-v2.jpg … 17-va.jpg …

A suffix **opens** a section that runs until the next suffixed page, so the example above is
cover 01–02, title 03, cello 04–08, violin 1 09–12, violin 2 13–16, viola 17–20. Pages
before the first suffix become `front`.

Output is named like the Rochester part-PDFs already in this collection —
`CZ-Pu_59_R_23.pdf` for the whole thing and `CZ-Pu_59_R_23.cello.pdf` for a part — so both
provenances read the same way on the shelf.

`img2pdf` embeds the original JPEG bytes without re-encoding, so the PDFs are lossless and
cost no quality over the images they came from.
"""
import argparse, json, re, sys
from pathlib import Path

# What the short suffixes mean. Keys are matched case-insensitively against the suffix.
PARTS = {
    'cover': 'cover', 'title': 'title', 'front': 'front', 'index': 'index',
    'v1': 'violin1', 'vl1': 'violin1', 'vln1': 'violin1', 'violin1': 'violin1',
    'v2': 'violin2', 'vl2': 'violin2', 'vln2': 'violin2', 'violin2': 'violin2',
    'va': 'viola', 'vla': 'viola', 'alto': 'viola', 'viola': 'viola',
    'vc': 'cello', 'vlc': 'cello', 'cello': 'cello', 'violoncello': 'cello',
    'b': 'basso', 'basso': 'basso', 'bass': 'basso', 'bc': 'continuo',
}
PAGE = re.compile(r'^(\d+)(?:[-_.](.+))?$')
IMG = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')


def pages(d):
    """[(n, part_or_None, path)] in page order, from `NN[-tag].ext` names."""
    out = []
    for f in d.iterdir():
        if f.suffix.lower() not in IMG or not f.is_file(): continue
        m = PAGE.match(f.stem)
        if not m:
            print(f'  ? skipping {f.name} — not NN or NN-tag', file=sys.stderr)
            continue
        tag = (m[2] or '').strip().lower()
        out.append((int(m[1]), PARTS.get(tag, tag or None), f))
    return sorted(out, key=lambda t: t[0])


def segments(pp):
    """[(part, [paths])] — a tagged page opens a section that runs to the next tagged one."""
    segs, cur = [], None
    for n, part, f in pp:
        if part or cur is None:
            cur = [part or 'front', []]
            segs.append(cur)
        cur[1].append(f)
    return [(p, fs) for p, fs in segs]


def stem_for(d):
    """Base filename: the one metadata.json already suggests, else the directory name."""
    mf = d / 'metadata.json'
    if mf.exists():
        try:
            m = json.loads(mf.read_text())
            s = m.get('suggested_filename')
            if s: return Path(s).stem
            sig, shelf = m.get('siglum'), m.get('shelfmark')
            if sig or shelf:
                return re.sub(r'_+', '_', re.sub(r'[^\w.-]', '_', f'{sig or ""}_{shelf or ""}')).strip('_')
        except Exception:
            pass
    return d.name


def write_pdf(paths, out, force):
    import img2pdf
    if out.exists() and not force:
        print(f'  = {out.name} (exists)', file=sys.stderr)
        return 0
    try:
        out.write_bytes(img2pdf.convert([str(p) for p in paths]))
    except Exception as ex:
        print(f'  ! {out.name}: {ex}', file=sys.stderr)
        return 0
    print(f'  + {out.name}  {len(paths)} pages, {out.stat().st_size / 1e6:.1f} MB', file=sys.stderr)
    return 1


def build(d, force=False, whole_only=False):
    pp = pages(d)
    if not pp:
        return 0
    stem = stem_for(d)
    segs = segments(pp)
    print(f'{d}: {len(pp)} pages, {len(segs)} sections '
          f'({", ".join(f"{p} x{len(f)}" for p, f in segs)})', file=sys.stderr)
    n = write_pdf([f for _, _, f in pp], d / f'{stem}.pdf', force)
    if not whole_only and len(segs) > 1:
        for part, files in segs:
            n += write_pdf(files, d / f'{stem}.{part}.pdf', force)
    return n


def candidates(root):
    """Item folders holding numbered page images — the ones a manual download lands in."""
    for mf in sorted(Path(root).rglob('metadata.json')):
        d = mf.parent
        if d.name == 'watermarks': continue
        if any(PAGE.match(f.stem) and f.suffix.lower() in IMG for f in d.iterdir()):
            yield d


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('dirs', nargs='*', type=Path, help='item folders (default: scan digitizations/)')
    p.add_argument('--root', type=Path, default=Path('digitizations'))
    p.add_argument('--force', action='store_true', help='rebuild PDFs that already exist')
    p.add_argument('--whole-only', action='store_true', help='skip the per-part PDFs')
    p.add_argument('--parts-only', action='store_true',
                   help='only folders whose pages carry part tags, not plain IIIF runs')
    a = p.parse_args()

    dirs = a.dirs or list(candidates(a.root))
    if a.parts_only or not a.dirs:
        # A plain `001.jpg…` IIIF run has no tags and gains nothing from a second copy as PDF.
        dirs = [d for d in dirs if any(part for _, part, _ in pages(d))]
    if not dirs:
        sys.exit('nothing to do — no folders with tagged page images')
    total = sum(build(d, a.force, a.whole_only) for d in dirs)
    print(f'{total} PDFs written', file=sys.stderr)
