# /// script
# requires-python = ">=3.11"
# ///
"""Move page images to Trash once their bytes are proven to live inside the collated PDF.

    uv run tools/oneoff/trash_collated_jpegs.py --dry-run
    uv run tools/oneoff/trash_collated_jpegs.py

Not deleted -- moved to `~/.Trash/boccherini-page-images-<date>/`, keeping the folder
structure, so the whole thing can be dragged back.

A file is only moved when all four hold:

  1. `<folder>/<folder>.pdf` exists,
  2. `pdf-verification.jsonl` records that folder as passing,
  3. that manifest lists this exact filename, and
  4. the file's MD5 still equals the checksum recorded when it was verified.

Point 4 matters: the manifest was written at verification time, and anything that changed
since is not covered by it. A file that fails any check stays where it is.

Before running this, `preserve_page_labels.py` must have copied what the filenames encode
into each sidecar, and `rism_digitizations.py` must know to trust a collated PDF -- without
that, the next harvest sees empty folders and re-downloads everything.
"""
import argparse, hashlib, json, os, shutil, sys
from datetime import date
from pathlib import Path

DIG = Path('digitizations')
MANIFEST = Path('pdf-verification.jsonl')



def irreplaceable():
    """Folders declared irreplaceable in `originals.jsonl`. Their page images are the only
    copies that exist; a collated PDF is not a substitute for them, whatever it verifies."""
    import json
    f = Path('originals.jsonl')
    if not f.exists():
        return set()
    return {json.loads(l)['folder'] for l in f.read_text().splitlines() if l.strip()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    if not MANIFEST.exists():
        sys.exit('no pdf-verification.jsonl — run `uv run tools/verify_pdfs.py` first')
    ver = {}
    for line in MANIFEST.read_text().splitlines():
        r = json.loads(line)
        if r.get('ok') and r.get('pages'):
            ver[r['folder']] = r['pages']

    dest = Path.home() / '.Trash' / f'boccherini-page-images-{date.today()}'
    moved = bytes_moved = 0
    kept = []
    protect = irreplaceable()
    for d in sorted({p.parent for p in DIG.rglob('*.jpg')}):
        rel = str(d.relative_to(DIG))
        if rel in protect:
            kept.append((rel, 'irreplaceable — originals are never traded for a PDF'))
            continue
        pages = ver.get(rel)
        if not pages:
            kept.append((rel, 'not recorded as verified')); continue
        if not (d / f'{d.name}.pdf').exists():
            kept.append((rel, 'no collated PDF')); continue
        # every page must still match what was verified
        files = sorted(d.glob('*.jpg'))
        mism = [f.name for f in files
                if pages.get(f.name) != hashlib.md5(f.read_bytes()).hexdigest()]
        if mism:
            kept.append((rel, f'{len(mism)} file(s) changed since verification')); continue
        for f in files:
            tgt = dest / rel / f.name
            bytes_moved += f.stat().st_size
            moved += 1
            if not a.dry_run:
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(tgt))
    verb = 'would move' if a.dry_run else 'moved'
    print(f'{verb} {moved} images ({bytes_moved/1e9:.2f} GB) -> {dest}', file=sys.stderr)
    if kept:
        print(f'\n{len(kept)} folders left alone:', file=sys.stderr)
        for r, why in kept:
            print(f'  {r:40} {why}', file=sys.stderr)


if __name__ == '__main__':
    main()
