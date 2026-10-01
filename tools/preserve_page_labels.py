# /// script
# requires-python = ">=3.11"
# ///
"""Move what the filenames say into the sidecar, before the filenames go away.

    uv run tools/preserve_page_labels.py --dry-run
    uv run tools/preserve_page_labels.py

Most page images are named `001.jpg`, `002.jpg` -- the name carries nothing but order, and
a collated PDF keeps order. Three folders are different:

  `550503024_CZ-Pu`   `01-cover`, `03-title`, `04-vc`, `09-v1`, `13-v2`, `17-va`
                      a hand-numbered download where the suffixes mark where each part
                      begins. `make_part_pdfs.py` reads nothing else.
  `650004089_A-ST`    `..._MusMs577_vl1_2vSm.jpg`
  `650004090_A-ST`    `..._MusMs576_vlc1r.jpg`
                      Muscat attachments whose names give the shelfmark, the part and the
                      folio -- facts that exist nowhere else in the record.

This writes a `pages` block: one entry per image, in order, with its original filename,
its PDF page number, and whatever the name encoded. After this the images are recoverable
from the PDF *and* still described.
"""
import argparse, json, re, sys
from pathlib import Path

DIG = Path('digitizations')
PART = {'vc': 'violoncello', 'v1': 'violin 1', 'v2': 'violin 2', 'va': 'viola',
        'b': 'basso', 'vla': 'viola', 'vlc': 'violoncello', 'vl1': 'violin 1',
        'vl2': 'violin 2'}


def label_hand(name):
    """`04-vc.jpg` -> {'opens': 'violoncello'}; `02.jpg` -> {}."""
    m = re.fullmatch(r'(\d+)-([A-Za-z0-9]+)\.jpg', name)
    if not m: return {}
    tag = m.group(2).lower()
    if tag in ('cover', 'title'): return {'opens': tag}
    return {'opens': PART.get(tag, tag)}


def label_muscat(name):
    """`Bocch_QuartEs_op8-2_A-ST_MusMs577_vl1_2vSm.jpg` -> shelfmark, part, folio."""
    out = {}
    m = re.search(r'MusMs(\d+)', name)
    if m: out['shelfmark'] = f'Mus.ms. {m.group(1)}'
    m = re.search(r'_(vl1|vl2|vla|vlc|b)[_\d]', name + '_')
    if m: out['part'] = PART.get(m.group(1), m.group(1))
    m = re.search(r'_(?:vl1|vl2|vla|vlc|b)_?(\d*)([rv])', name)
    if m: out['folio'] = f"{m.group(1) or '1'}{m.group(2)}"
    m = re.search(r'op(\d+)-(\d+)', name)
    if m: out['opus'] = f'Op. {m.group(1)} no. {m.group(2)}'
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--from-dir', type=Path,
                    help='read filenames from here when the images have been moved '
                         '(e.g. ~/.Trash/boccherini-page-images-YYYY-MM-DD)')
    a = ap.parse_args()
    n = 0
    folders = sorted({p.parent for p in DIG.rglob('*.jpg')})
    if a.from_dir:
        # The images are gone; their names survive wherever they were moved to.
        folders = sorted({DIG / p.parent.relative_to(a.from_dir)
                          for p in a.from_dir.rglob('*.jpg')} | set(folders))
    for d in folders:
        src = d if list(d.glob('*.jpg')) else (
            a.from_dir / d.relative_to(DIG) if a.from_dir else d)
        names = sorted(p.name for p in src.glob('*.jpg'))
        if not names: continue
        f = d / 'metadata.json'
        if not f.exists(): continue
        plain = all(re.fullmatch(r'\d{3}\.jpg', x) for x in names)
        m = json.loads(f.read_text())
        pages = []
        for i, name in enumerate(names, 1):
            e = {'page': i, 'file': name}
            e.update(label_hand(name) or label_muscat(name) if not plain else {})
            pages.append(e)
        block = {'source': 'filenames, preserved before the images were moved to Trash',
                 'count': len(pages), 'pages': pages}
        if plain:
            # Nothing to preserve beyond the order the PDF already keeps.
            block = {'source': 'sequential filenames; order is preserved by the PDF',
                     'count': len(pages)}
        if m.get('page_index') == block: continue
        m['page_index'] = block
        n += 1
        extra = [p for p in pages if len(p) > 2]
        print(f"  {str(d.relative_to(DIG)):34} {len(pages):>4} pages"
              + (f'  · {len(extra)} carry labels' if extra else ''), file=sys.stderr)
        if not a.dry_run:
            f.write_text(json.dumps(m, indent=1, ensure_ascii=False) + '\n')
    print(f"{n} sidecars {'would gain' if a.dry_run else 'gained'} a page index", file=sys.stderr)


if __name__ == '__main__':
    main()
