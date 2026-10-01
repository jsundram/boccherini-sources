# /// script
# requires-python = ">=3.11"
# ///
"""The only supported way to change a label or a linkage.

    # what is in this PDF
    uv run tools/claim.py label G242-244/990005886_D-B_livr1 --gerard 242,243,244 \
        --saw "title page reads 'Op 58. 1re Partie'; four part-books, each running I/II/III"

    # where it came from
    uv run tools/claim.py link found/BnF/btv1b52502357c --rism 840013721 --relation copy \
        --saw "F-Po RES-507 (14), the shelfmark on the Gallica record"

    # it is fine as it stands
    uv run tools/claim.py confirm G159-164/990005852_US-R --saw "four parts, Hummel imprint, complete"

    uv run tools/claim.py show <folder>        # every claim on one item, and where each lives

Two kinds of change matter here and everything downstream depends on both: **labels** (what
is in a PDF) and **linkages** (which RISM record it is a copy of). They could be written in
four different places with four different precedences, and nothing checked that a change was
well-formed or said where it came from. That is fine while one person remembers; it is not
something a tool can trust.

So this is the front door. It:

  * refuses a Gérard number that is not in `opera.json`, and a RISM id that is not in the
    cache -- a typo used to become a permanent silent mislabel;
  * requires `--saw`: what you actually observed. A claim with no evidence is a guess with
    a timestamp;
  * writes to the layer that owns the fact -- `corrections.json` when it belongs to the
    RISM record (the harvester rebuilds folder names from there, so a Gérard number written
    anywhere else is reverted on the next run), `metadata.json` when it belongs to our copy;
  * stamps the date and the tool, so the claim is auditable afterwards.

It never edits a derived file. Run `uv run tools/pipeline.py` afterwards and everything else
follows.
"""
import argparse, json, re, sys
from datetime import date
from pathlib import Path

DIG = Path('digitizations')
CORR = Path('corrections.json')
CACHE = Path('.rism-cache')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')


def die(msg):
    sys.exit(f'refused: {msg}')


def find(folder):
    d = DIG / folder
    if not d.exists():
        hits = [p.parent for p in DIG.rglob('metadata.json')
                if p.parent.name == Path(folder).name]
        if len(hits) == 1:
            d = hits[0]
        elif not hits:
            die(f'no such item: {folder}')
        else:
            die(f'ambiguous: {folder} matches {[str(h) for h in hits]}')
    if not (d / 'metadata.json').exists():
        die(f'{d} has no metadata.json')
    return d


def known_gerard():
    out = set()

    def walk(x):
        if isinstance(x, dict):
            if 'gerard' in x and x['gerard'] is not None:
                out.add(str(x['gerard']))
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(json.loads(Path('opera.json').read_text()))
    return out


def load(d):
    return json.loads((d / 'metadata.json').read_text())


def save(d, m):
    (d / 'metadata.json').write_text(json.dumps(m, indent=1, ensure_ascii=False) + '\n')


def stamp(saw, how):
    return dict(date=date.today().isoformat(), how=how, found=saw, by='claim.py')


def cmd_label(a):
    d = find(a.folder)
    m = load(d)
    gs = [g.strip() for g in a.gerard.split(',') if g.strip()]
    if not gs: die('--gerard needs at least one number')
    known = known_gerard()
    unknown = [g for g in gs if g not in known]
    if unknown and not a.force:
        die(f'not in opera.json: {", ".join(unknown)} — a typo here becomes a silent '
            f'mislabel. Use --force if the catalogue is the thing that is wrong.')
    sid = m.get('source_id')
    if sid and not a.copy_only:
        # The harvester rebuilds folder names from RISM on every run, so a Gérard number
        # that lives only in the sidecar is reverted. It belongs in corrections.json.
        corr = json.loads(CORR.read_text()) if CORR.exists() else {}
        entry = corr.setdefault(str(sid), {})
        entry['contents'] = [{'n': i + 1, 'gerard': g} for i, g in enumerate(gs)]
        entry['established_by'] = f'{a.saw} [claim.py, {date.today().isoformat()}]'
        entry.setdefault('note', f'Contents of {d.name}, established by looking.')
        CORR.write_text(json.dumps(corr, indent=1, ensure_ascii=False) + '\n')
        where = f'corrections.json[{sid}]'
    else:
        m['gerard'] = gs[0]
        m['gerard_numbers'] = gs
        m['gerard_established_by'] = f'{a.saw} [claim.py, {date.today().isoformat()}]'
        where = 'metadata.json'
    m['contents_verified'] = stamp(a.saw, a.how or 'looked at the pages')
    save(d, m)
    print(f'  label  {d.relative_to(DIG)}  G {", ".join(gs)}  -> {where}')
    print('  run `uv run boc.py build` to refile the folder and rebuild everything')


def cmd_link(a):
    d = find(a.folder)
    m = load(d)
    sid = a.rism.rstrip('/').rsplit('/', 1)[-1]
    if not (CACHE / f'{sid}.xml').exists() and not a.force:
        die(f'RISM {sid} is not in the cache — check the id, or harvest it first')
    if a.relation not in ('copy', 'work'):
        die("--relation must be 'copy' (this is that source) or 'work' (RISM's record for "
            "the same edition at another library)")
    urls = [u for u in (m.get('rism_related') or []) if isinstance(u, str)]
    url = f'https://rism.online/sources/{sid}'
    if url not in urls: urls.append(url)
    m['rism_related'] = urls
    m['rism_relation'] = a.relation
    m['rism_related_established_by'] = f'{a.saw} [claim.py, {date.today().isoformat()}]'
    if a.siglum: m['siglum'] = a.siglum
    if a.shelfmark: m['shelfmark'] = a.shelfmark
    save(d, m)
    print(f'  link   {d.relative_to(DIG)}  -> RISM {sid} as "{a.relation}"')
    print('  run `uv run boc.py build` to rebuild the concordance and the shelf')


def cmd_confirm(a):
    d = find(a.folder)
    m = load(d)
    m['contents_verified'] = stamp(a.saw, a.how or 'looked at the pages')
    save(d, m)
    print(f'  confirm {d.relative_to(DIG)}  (now tier A)')


def cmd_show(a):
    d = find(a.folder)
    m = load(d)
    import evidence
    t, lab = evidence.tier_of(m, evidence.reading(d.name))
    print(f'{d.relative_to(DIG)}   tier {t} — {lab}\n')
    rows = [('gerard', m.get('gerard_label') or m.get('gerard'), 'metadata.json'),
            ('gerard said by', m.get('gerard_established_by'), 'metadata.json'),
            ('siglum/shelfmark', f"{m.get('siglum')} {m.get('shelfmark')}", 'metadata.json'),
            ('rism', m.get('rism_related'), 'metadata.json'),
            ('relation', m.get('rism_relation'), 'metadata.json'),
            ('verified', m.get('contents_verified'), 'metadata.json')]
    sid = m.get('source_id')
    if sid and CORR.exists():
        c = json.loads(CORR.read_text()).get(str(sid))
        if c: rows.append(('correction', c.get('established_by'), f'corrections.json[{sid}]'))
    for k, v, where in rows:
        if v: print(f'  {k:18} {str(v)[:110]}\n  {"":18} ({where})')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name, fn in (('label', cmd_label), ('link', cmd_link),
                     ('confirm', cmd_confirm), ('show', cmd_show)):
        p = sub.add_parser(name)
        p.add_argument('folder')
        p.set_defaults(fn=fn)
        if name != 'show':
            p.add_argument('--saw', required=True,
                           help='what you actually observed — required, and the useful part')
            p.add_argument('--how', help='how you looked (contact sheet, title page, …)')
            p.add_argument('--force', action='store_true')
        if name == 'label':
            p.add_argument('--gerard', required=True, help='comma-separated, in order')
            p.add_argument('--copy-only', action='store_true',
                           help='write to this copy only, not to the RISM record')
        if name == 'link':
            p.add_argument('--rism', required=True)
            p.add_argument('--relation', default='copy')
            p.add_argument('--siglum')
            p.add_argument('--shelfmark')
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
