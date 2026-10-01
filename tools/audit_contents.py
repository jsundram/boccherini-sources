# /// script
# requires-python = ">=3.11"
# ///
"""Ask of every item: does what is on disk match what we say it is?

    uv run tools/audit_contents.py                 # -> digitizations/CONTENT-AUDIT.md
    uv run tools/audit_contents.py --flagged       # print only the items worth looking at

Most of this archive's metadata is inherited -- from RISM, from a portal's search page, or
from a filename someone typed. Very little of it has been checked against the pages. This
does not check it either: no script can tell that page 14 opens `III. Quartetto`. What it
can do is measure the things that *disagree*, and rank them, so the looking goes where it
pays.

The flags, each learned from something that turned out to be wrong:

  span-shared      Two folders carry the same Gérard span but differ greatly in size. Op. 58
                   looked like this: livraisons 1 and 2 were both labelled G 242-247, and
                   they are two different books of three quartets each.
  thin             Very few pages for the number of works claimed. Usually means a single
                   part-book, not the whole set -- `btv1b108778048` is 15 pages for six
                   quartets.
  count-mismatch   The folder name spans more works than the item records Gérard numbers
                   for. RISM often gives a six-quartet print one number.
  parts-short      A part-set with fewer than four part files.

Verification is recorded, not assumed. When an item has been read -- with
`contact_sheet.py`, or by opening it -- put a `contents_verified` block in its
`metadata.json`:

    "contents_verified": {"date": "2026-09-29", "how": "head-strip contact sheet",
                          "found": "quartets I-III in four part-books"}

Items carrying one are listed as verified and drop out of the worklist.
"""
import argparse, collections, json, re, subprocess, sys
from pathlib import Path

DIG = Path('digitizations')
STORE = Path('structure')


def structure(scan_id):
    """What `read_structure.py` observed, if it has been run.

    Machine output: regenerable, never hand-edited. A human disagreeing with it writes
    `contents_verified` in the item's metadata.json, or -- when the fact belongs to the
    RISM record rather than to our copy -- an entry in corrections.json. Both outrank this."""
    f = STORE / f'{scan_id}.json'
    if not f.exists(): return None
    try:
        return json.loads(f.read_text())
    except Exception:
        return None


def page_count(d):
    n = len(list(d.glob('*.jpg')))
    if n: return n
    for p in d.glob('*.pdf'):
        if 'cover' in p.stem.lower(): continue
        try:
            o = subprocess.run(['pdfinfo', str(p)], capture_output=True, text=True,
                               timeout=60).stdout
            n += int(next(l.split(':')[1] for l in o.splitlines() if l.startswith('Pages')))
        except Exception:
            pass
    return n


def span_size(label):
    """How many works the folder name claims: '242-244' -> 3, '201, 203, 234' -> 3."""
    if not label: return 0
    m = re.fullmatch(r'(\d+)-(\d+)', label.strip())
    if m: return int(m.group(2)) - int(m.group(1)) + 1
    return len([x for x in label.split(',') if x.strip()])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--flagged', action='store_true')
    a = ap.parse_args()
    rows = []
    for f in sorted(DIG.rglob('metadata.json')):
        d = f.parent
        if not [x for x in d.iterdir() if x.suffix.lower() in ('.pdf', '.jpg')]: continue
        m = json.loads(f.read_text())
        gs = [str(x) for x in (m.get('gerard_numbers') or [])] or \
             ([str(m['gerard'])] if m.get('gerard') else [])
        label = m.get('gerard_label') or (gs[0] if gs else None)
        # A dot in the stem is the part-book convention (`<base>.violin1.pdf`). When an
        # item declares its parts instead -- because one PDF holds all four -- believe the
        # declaration: counting per-work files as part-books flagged a complete set short.
        named = [x for x in (m.get('parts') or []) if isinstance(x, str)]
        parts = len(named) if named else len([p for p in d.glob('*.pdf')
                     if '.' in p.stem and 'cover' not in p.stem.lower()])
        # Copy-level claims only. An edition-level link is shared by every copy of that
        # edition, so counting it made a dozen unrelated folders look like the same object.
        ids = set()
        if m.get('source_id'): ids.add(str(m['source_id']))
        if m.get('rism_relation') != 'work':
            for u in ([m.get('source')] if isinstance(m.get('source'), str) else []) + \
                     (m.get('rism_related') if isinstance(m.get('rism_related'), list) else []):
                if isinstance(u, str) and '/sources/' in u:
                    ids.add(u.rstrip('/').rsplit('/', 1)[-1])
        st = structure(d.name)
        rows.append(dict(folder=str(d.relative_to(DIG)), label=label, gs=gs, ids=ids,
                         st=st,
                         claimed=max(span_size(label), len(gs)), n=page_count(d),
                         parts=parts, siglum=m.get('siglum'),
                         medium=m.get('medium') or m.get('record_type'),
                         verified=m.get('contents_verified')))

    # Two copies of the *same RISM source* under the same Gérard span should be the same
    # object. Two different editions of the same works legitimately differ in size, so
    # grouping by span alone flagged half the archive and meant nothing.
    by_src = collections.defaultdict(list)
    for r in rows:
        for i in r['ids']:
            by_src[(i, r['label'])].append(r)

    for r in rows:
        flags = []
        for i in r['ids']:
            peers = [x for x in by_src.get((i, r['label']), []) if x is not r]
            sizes = [x['n'] for x in peers if x['n']]
            if sizes and r['n'] and max(sizes + [r['n']]) / max(min(sizes + [r['n']]), 1) >= 2.0:
                flags.append('span-shared'); break
        if r['claimed'] and r['n'] and r['n'] / r['claimed'] < 5:
            flags.append('thin')
        if r['claimed'] > len(r['gs']):
            flags.append('count-mismatch')
        if r['parts'] and r['parts'] < 4:
            flags.append('parts-short')
        st = r.get('st')
        if st and st.get('read') and st.get('disagreements'):
            flags.append('ocr-disagrees')
        r['flags'] = flags
        r['why'] = (st or {}).get('disagreements') or []

    todo = [r for r in rows if r['flags'] and not r['verified']]
    todo.sort(key=lambda r: (-len(r['flags']), r['folder']))

    if a.flagged:
        for r in todo:
            print(f"  {','.join(r['flags']):34} {r['n']:>4}p/{r['claimed']} works  {r['folder']}")
        print(f'\n{len(todo)} flagged, {sum(1 for r in rows if r["verified"])} verified, '
              f'{len(rows)} total', file=sys.stderr)
        return

    L = ['# Content audit — does the disk match the label?', '',
         f"{len(rows)} items. **{sum(1 for r in rows if r['verified'])} have been checked "
         f"against their pages**; the rest carry metadata inherited from RISM, a portal "
         f"search page, or a filename.", '',
         'Nothing here proves an item is wrong. These are disagreements between what an item '
         'says and what is on disk, ranked so that looking goes where it pays. Read one with',
         '', '```sh', 'uv run boc.py look digitizations/<folder>', '```', '',
         'which stacks the top of every page into one column — quartet headings, part names '
         'and tempo marks all line up and the structure reads in a glance.', '',
         '## The flags', '',
         '| flag | means | learned from |', '|---|---|---|',
         '| `span-shared` | another folder claims the same Gérard span and is a very '
         'different size | Op. 58: two livraisons both labelled G 242–247, each actually '
         'holding three quartets |',
         '| `thin` | very few pages for the works claimed — usually one part-book, not the set '
         '| `btv1b108778048`, 15 pages for six quartets |',
         '| `count-mismatch` | the folder spans more works than the item has Gérard numbers '
         'for | RISM gives a six-quartet print one number |',
         '| `parts-short` | a part-set with fewer than four part files | the Boyer Op. 9, '
         'V2 and VC only |',
         '| `ocr-disagrees` | the print\'s own headings do not match its label — see the '
         'last column | Op. 58, two works per part-book against three declared |', '',
         'The reading lives in `../structure/<scan-id>.json`: what was seen, on which page, '
         'and what RISM says for comparison. It is machine output and regenerable — correct '
         'it by recording `contents_verified` in the item\'s `metadata.json`, or, when the '
         'fact belongs to the RISM record rather than to our copy, in `../corrections.json`. '
         'Both outrank the reading.', '']

    if todo:
        L += ['---', '', f'## Worth looking at — {len(todo)}', '',
              '| folder | G | pages | works | parts | flags | what the reading says |',
              '|---|---|---:|---:|---:|---|---|']
        for r in todo:
            why = '; '.join(r['why'])[:150].replace('|', '\\|')
            L.append(f"| `{r['folder']}` | {r['label'] or '—'} | {r['n']} | {r['claimed']} "
                     f"| {r['parts'] or '—'} | {', '.join(r['flags'])} | {why or '—'} |")
        L.append('')

    ver = [r for r in rows if r['verified']]
    if ver:
        L += ['---', '', f'## Checked against the pages — {len(ver)}', '',
              '| folder | when | how | what was found |', '|---|---|---|---|']
        for r in sorted(ver, key=lambda r: r['folder']):
            v = r['verified'] if isinstance(r['verified'], dict) else {}
            L.append(f"| `{r['folder']}` | {v.get('date', '—')} | {v.get('how', '—')} "
                     f"| {v.get('found', '—')} |")
        L.append('')

    clean = [r for r in rows if not r['flags'] and not r['verified']]
    L += ['---', '', f'## Nothing disagrees — {len(clean)}', '',
          'No flag fired. That is not the same as having been checked: it means the page '
          'count, the Gérard span and the part files are consistent with each other.', '']

    (DIG / 'CONTENT-AUDIT.md').write_text('\n'.join(L))
    print(f'{len(rows)} items, {len(todo)} flagged, {len(ver)} verified '
          f'-> {DIG}/CONTENT-AUDIT.md', file=sys.stderr)


if __name__ == '__main__':
    main()
