# /// script
# requires-python = ">=3.11"
# ///
"""Compute the archive's numbers, and inject them into the docs that quote them.

    uv run tools/stats.py              # fill every <!-- stats:NAME --> block
    uv run tools/stats.py --check      # non-zero if any block is out of date
    uv run tools/stats.py --print      # the numbers, as JSON

A document that states a count goes stale the moment the count changes, silently, and stays
wrong until somebody notices. `STATE-OF-EVIDENCE.md` said 82 where the answer was 76 within
an hour of being written.

So authored docs do not contain counts. They contain a marked region:

    <!-- stats:headline -->
    ...generated, do not edit...
    <!-- /stats:headline -->

which this fills. `check_archive.py` fails while any block is out of date, so a number in
the documentation cannot drift from the data it describes. Prose outside the markers is
written by hand and left alone.

Historical findings — "the Berlin search returned 74 results on 2026-09-28" — are a record
of what was true at a moment and keep their numbers. The rule is for *status*, not history.
"""
import argparse, collections, json, re, subprocess, sys
from pathlib import Path

import evidence

DIG = Path('digitizations')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')
BLOCK = re.compile(r'(<!-- stats:(\w+) -->\n)(.*?)(<!-- /stats:\2 -->)', re.S)


def facts():
    items, tiers, med = [], collections.Counter(), collections.Counter()
    files = pdfs = 0
    for f in sorted(DIG.rglob('metadata.json')):
        d = f.parent
        got = [x for x in d.iterdir() if x.suffix.lower() in MEDIA]
        if not got: continue
        m = json.loads(f.read_text())
        st = evidence.reading(d.name)
        t, _ = evidence.tier_of(m, st)
        tiers[t] += 1
        med[('autograph' if m.get('is_autograph')
             else m.get('medium') or m.get('record_type') or 'unknown')] += 1
        files += len(got)
        pdfs += len([x for x in got if x.suffix.lower() == '.pdf'])
        items.append((m, st))
    inc = 0
    p = Path('boccherini-rism-incipits.jsonl')
    if p.exists(): inc = sum(1 for _ in p.open())
    rism = len(list(Path('.rism-cache').glob('*.xml')))
    read = sum(1 for _, st in items if st and st.get('read'))
    unread = sum(1 for _, st in items if st and not st.get('read'))
    dis = sum(1 for _, st in items if st and (st.get('disagreements') or []))
    unid = sum(1 for m, _ in items
               if not (m.get('gerard') or m.get('gerard_numbers'))
               and m.get('form') != 'not-a-quartet')
    unlinked = 0
    up = DIG / 'UNLINKED-HOLDINGS.md'
    if up.exists():
        mm = re.search(r'^(\d[\d,]*) holdings across (\d+) libraries', up.read_text(), re.M)
        unlinked = (mm.group(1), mm.group(2)) if mm else (0, 0)
    return dict(items=len(items), files=files, pdfs=pdfs, incipits=inc, rism_sources=rism,
                tiers=dict(tiers), medium=dict(med), ocr_read=read, ocr_unreadable=unread,
                disagreeing=dis, unidentified=unid, verified=tiers['A'],
                solid=tiers['A'] + tiers['B'] + tiers['C'],
                needs_eyes=tiers['D'] + tiers['E'] + tiers['F'],
                unlinked_holdings=unlinked[0], unlinked_libraries=unlinked[1])


def render(name, f):
    if name == 'headline':
        return (f"| | |\n|---|---:|\n"
                f"| Items on disk | **{f['items']}** |\n"
                f"| Incipits harvested | **{f['incipits']}** |\n"
                f"| RISM quartet sources | **{f['rism_sources']}** |\n"
                f"| Holdings RISM lists with no scan | **{f['unlinked_holdings']}** "
                f"at {f['unlinked_libraries']} libraries |\n"
                f"| Label rests on evidence | **{f['solid']}** of {f['items']} |\n"
                f"| Still needs a person to look | **{f['needs_eyes']}** |\n"
                f"| Unidentified | **{f['unidentified']}** |\n")
    if name == 'evidence':
        t = f['tiers']
        return ('| tier | items | meaning |\n|---|---:|---|\n' + ''.join(
            f"| **{k}** | {t.get(k, 0)} | {evidence.LABEL[k]} |\n" for k in 'ABCDEF'))
    if name == 'ocr':
        m = f['medium']
        return (f"- **{f['ocr_read']}** items were read by OCR; "
                f"**{f['ocr_unreadable']}** are manuscripts it cannot read\n"
                f"- medium: " + ', '.join(f'**{v}** {k}' for k, v in sorted(m.items())) + "\n"
                f"- **{f['disagreeing']}** items whose pages disagree with their label\n")
    if name == 'storage':
        return (f"**{f['items']} folders, {f['files']} files** "
                f"({f['pdfs']} PDFs). Page images live inside the collated PDFs; "
                f"see `PAGE-IMAGES-AND-PDFS.md`.\n")
    return ''


def inject(check=False):
    f = facts()
    stale = []
    for doc in [Path('README.md')] + sorted(DIG.glob('*.md')):
        s = doc.read_text()
        if 'stats:' not in s: continue
        def sub(m):
            body = render(m.group(2), f)
            return m.group(1) + body + m.group(4)
        out = BLOCK.sub(sub, s)
        if out != s:
            stale.append(str(doc))
            if not check: doc.write_text(out)
    return f, stale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--print', dest='show', action='store_true')
    a = ap.parse_args()
    f, stale = inject(check=a.check)
    if a.show:
        print(json.dumps(f, indent=1))
        return
    if a.check:
        for d in stale: print(f'  out of date: {d}', file=sys.stderr)
        print(f'{len(stale)} doc(s) out of date', file=sys.stderr)
        sys.exit(1 if stale else 0)
    print(f"{len(stale)} doc(s) updated", file=sys.stderr)


if __name__ == '__main__':
    main()
