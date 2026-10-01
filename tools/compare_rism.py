# /// script
# requires-python = ">=3.11"
# ///
"""Check our labels against RISM's own reading of the same source.

    uv run tools/compare_rism.py            # -> digitizations/RISM-DISAGREEMENTS.md
    uv run tools/compare_rism.py --print    # to the terminal

Cheap, and it should have been the first thing written. Every item that claims to be a copy
of a RISM source can have its `medium` checked against that record's `593` source type --
no OCR, no page rendering, one pass over the cache.

It found three disagreements on the first run, and they did not all resolve the same way:

  `btv1b108677212`, `btv1b10867724d`   labelled print by the Gallica classifier; plainly
                                       handwritten, and RISM says Manuscript copy. **Ours
                                       was wrong.**
  `bne-7d1c14c0-103`                   RISM's linked records say Manuscript copy; the title
                                       page is an engraved Hummel imprint. **RISM's link is
                                       to another copy.**

Which is the rule this project runs on: looking beats a catalogue that never saw our copy.
So this reports disagreements; it does not resolve them, and it never edits anything.

Items linked to RISM at *edition* level are skipped -- a different copy of the same edition
may legitimately be a different medium.
"""
import argparse, importlib.util, json, sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('rd', 'tools/rism_digitizations.py')
rd = importlib.util.module_from_spec(spec); spec.loader.exec_module(rd)
CACHE = Path('.rism-cache'); rd.cache_dir[0] = CACHE
DIG = Path('digitizations')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')


def ours(m):
    if m.get('is_autograph'): return 'autograph'
    if m.get('medium') in ('print', 'manuscript', 'autograph'): return m['medium']
    return {'print': 'print', 'manuscript': 'manuscript'}.get(m.get('record_type'))


def theirs(types):
    if any('utograph' in t for t in types): return 'autograph'
    if any('anuscript' in t for t in types): return 'manuscript'
    if any('Print' in t for t in types): return 'print'
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--print', dest='to_stdout', action='store_true')
    a = ap.parse_args()
    rows, checked = [], 0
    for f in sorted(DIG.rglob('metadata.json')):
        d = f.parent
        if not any(x.suffix.lower() in MEDIA for x in d.iterdir() if x.is_file()): continue
        m = json.loads(f.read_text())
        if m.get('rism_relation') == 'work': continue
        o = ours(m)
        if not o: continue
        ids = []
        for k in ('source', 'rism_related'):
            v = m.get(k)
            for u in (v if isinstance(v, list) else [v]):
                if isinstance(u, str) and '/sources/' in u:
                    ids.append(u.rstrip('/').rsplit('/', 1)[-1])
        types = set()
        for sid in ids[:3]:
            try:
                types |= set(rd.describe(sid, rd.marc(sid, CACHE))['source_types'])
            except Exception:
                pass
        if not types: continue
        checked += 1
        t = theirs(types)
        # RISM's 'autograph' and our 'manuscript' are not a disagreement worth reporting:
        # every autograph is a manuscript, and the finer reading is RISM's to make.
        if t and o != t and not (t == 'autograph' and o == 'manuscript'):
            rows.append(dict(folder=str(d.relative_to(DIG)), ours=o, rism=t,
                             types=sorted(types), ids=ids[:3],
                             settled=bool(m.get('medium_established_by')),
                             note=m.get('medium_established_by')))
    L = ['# Where our label and RISM disagree', '',
         f'{checked} items claim to be a copy of a RISM source and record a medium. '
         f'**{len(rows)} disagree with RISM about what kind of thing they are.**', '',
         'Edition-level links are excluded: another library\'s copy of the same edition may '
         'legitimately be a different medium.', '',
         'A disagreement is not a verdict. RISM has never seen our copy, and on the first '
         'run of this check two disagreements were ours to fix and one was RISM linking to '
         'a different copy. Settle them by looking, then record the reason in '
         '`medium_established_by` — an entry carrying one is marked **settled** below.', '']
    if rows:
        L += ['| folder | ours | RISM | RISM source type | settled |', '|---|---|---|---|---|']
        for r in rows:
            L.append(f"| `{r['folder']}` | {r['ours']} | {r['rism']} | "
                     f"{', '.join(r['types'])} | {'yes' if r['settled'] else '—'} |")
        L.append('')
        for r in rows:
            if r['note']:
                L += [f"**`{r['folder']}`** — {r['note']}", '']
    else:
        L.append('No disagreements.')
    (DIG / 'RISM-DISAGREEMENTS.md').write_text('\n'.join(L))
    if a.to_stdout:
        for r in rows:
            print(f"  {r['folder']:38} ours={r['ours']:11} RISM={r['rism']:11} "
                  f"{'settled' if r['settled'] else 'OPEN'}")
    print(f'{checked} compared, {len(rows)} disagree -> {DIG}/RISM-DISAGREEMENTS.md',
          file=sys.stderr)


if __name__ == '__main__':
    main()
