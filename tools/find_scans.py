# /// script
# requires-python = ">=3.11"
# ///
"""Look for scans at libraries RISM does not link, starting with the autographs.

    uv run tools/find_scans.py                       # search, write the report
    uv run tools/find_scans.py --download            # ... and fetch what was found
    uv run tools/find_scans.py --siglum F-Po         # one library

RISM links a digitization for about 5% of the quartet holdings it catalogues
(`digitizations/UNLINKED-HOLDINGS.md`). The rest may well be scanned -- just not
linked from RISM. This searches the libraries' own portals for the holdings that
matter most: the ones RISM marks **Autograph manuscript**.

Writes `digitizations/AUTOGRAPH-SEARCH.md`: what was found, with deep links and
IIIF manifests where they exist, and what still needs a human.

### Why only some libraries

Portals are not uniform and most cannot be searched from a script. Each one here
was tried before being relied on:

  F-Po, F-Pn, F-Pc   Départements of the BnF, so their scans are on Gallica, which
                     has a real SRU API and IIIF manifests. This is the productive
                     one: seven Boccherini quartet autographs from the
                     Bibliothèque-musée de l'Opéra, dated 1792-1796.
  D-MÜs, D-Bhm       No scriptable search found -- Münster's Visual Library
                     exposes OAI but no keyword search, and the Universität der
                     Künste has no IIIF portal. Reported with their RISM library
                     page, which carries the library's own catalogue link.

A match is a *candidate*, not a fact. Gallica's metadata is free text and RISM's
shelfmarks do not appear in it, so the report prints Gallica's own title and
département for each hit and leaves the final identification to a person. That is
the same second-pass problem as `digitizations/unidentified/`, and the titles here
are unusually informative -- Boccherini dated these by month and year.
"""
import argparse, collections, json, re, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

BASE = 'https://rism.online'
# RISM's id for Boccherini. Needed because a person's sources include everything they
# are related to: the Pleyel prints dedicated to him name him in a 700 with $4 dte.
BOCCHERINI = 'people/30000391'
M = '{http://www.loc.gov/MARC21/slim}'
BROWSER = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')
SRW = {'srw': 'http://www.loc.gov/zing/srw/'}
# Gallica names the holding department in dc:source. Several RISM sigla sit behind the
# same BnF department, so a hit is attributed to a department, not to one siglum.
BNF_DEPT = re.compile(r"département (Musique|Bibliothèque-musée de l'opéra)", re.I)
# The BnF-family sigla in the quartet corpus. Any of them means Gallica is worth searching.
BNF_SIGLA = {'F-Pn', 'F-Pc', 'F-Po', 'F-Pmeyer', 'F-Prothschild'}

# Recall depends almost entirely on these. 'Bocherini' is the spelling on the 18th-century
# title pages and returns *more* records than the modern one. Boccherini also called these
# quartets Quartettini, Divertimenti and 'Sinfonie o quartetti', so searching only for
# 'quatuor' misses whole editions.
QUERIES = ('Boccherini quatuor', 'Boccherini quartetti', 'Boccherini quartettino',
           'Bocherini quartetti', 'Bocherini quatuor', 'Boccherini divertimenti',
           'Boccherini sinfonie quartetti', 'Boccherini')
# Libraries with no scriptable search. The RISM page carries their catalogue link.
NO_API = {'D-MÜs': "Münster's Visual Library serves OAI but no keyword search endpoint.",
          'D-Bhm': 'No IIIF or searchable digital collection found for the Universität der Künste.'}
QUARTET = re.compile(r'^(?:vl \(2\)|2 vl)\s*,\s*(?:[at]-)?(?:vla|violetta|taille)'
                     r'\s*,\s*(?:vlc|bc|b)$', re.I)
TITLE_Q = re.compile(r'^\s*\d*\s*quartet', re.I)
# Classifying Gallica's free-text titles. Four-part naming is not enough on its own:
# Boccherini's quartets appear as Quartetti, Quartettini, Divertimenti and
# 'Sinfonie o quartetti', while 'quatuor' also labels arrangements for winds.
# 'quarteto' (one t), 'quartetten', 'quartettos' and 'Divertimento' are all attested in
# RISM's own titles for these works, so the stem has to be loose.
FOUR_PART = re.compile(r'quartett|quatuor|quartet|divertiment', re.I)
# RISM files 7 of these quartets under the uniform title 'Sonatas' and Boccherini's Op. 2
# was printed as 'Sei Sinfonie o Quartetti'. A sonata or sinfonia is only a quartet when the
# title actually spells out four string parts, so that is what is required here.
WEAK_FORM = re.compile(r'sonat|sinfoni|symphon', re.I)
FOUR_STRINGS = re.compile(
    r'(?=.*violin|.*violon)(?=.*(?:viola|alto|violetta|taille))'
    r'(?=.*(?:violoncell|violoncell?e|basso|basse|\bcello\b|\bbass\b))', re.I | re.S)
QUINTET = re.compile(r'quintett|quintuor|quintet|sestett|sextuor', re.I)
TRIO = re.compile(r'terzett|\btrio\b', re.I)
# The scoring, when the title states it. This is what separates a real string quartet from
# '6 Quatuors ... arrangés pour flûte' and 'Trois quatuors pour clarinette, flûte cor et basson'.
STRINGS = re.compile(r'(?:2|two|deux|due|ii|sei|six)[.\s]*violin|due violini|deux violons', re.I)
NOT_STRINGS = re.compile(r'fl[uû]te|clarinett?e|basson|cor\b|hautbois|guitar|piano|'
                         r'clavecin|forte.?piano|harpe|chant|voix', re.I)
AUTOGRAPH = re.compile(r'autograph', re.I)
MANUSCRIPT = re.compile(r'manuscri|\bMS-|\bMS\b', re.I)


def fetch(url, accept='*/*', tries=4):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers={'Accept': accept, 'User-Agent': BROWSER}),
                         timeout=90) as r:
                return r.read()
        except Exception:
            if i == tries - 1: raise
            time.sleep(2 ** i)


def fields(rec, tag):
    return [{s.get('code'): s.text or '' for s in df.iter(M + 'subfield')}
            for df in rec.iter(M + 'datafield') if df.get('tag') == tag]


def by_composer(rec):
    """MARC 100 is the composer. A 100 naming someone else means this is not his work --
    which is how thirteen Pleyel prints dedicated to Boccherini got into this corpus."""
    m = (fields(rec, '100') or [{}])[0]
    return not m or m.get('0') in (None, '', BOCCHERINI)


def is_quartet(rec):
    ut = (fields(rec, '240') or [{}])[0]
    sc = (ut.get('m') or (fields(rec, '594') or [{}])[0].get('a') or '').strip()
    if sc: return bool(QUARTET.match(sc))
    return bool(TITLE_Q.match(ut.get('a') or (fields(rec, '245') or [{}])[0].get('a') or ''))


def gnum(g):
    m = re.match(r'\s*(\d+)(.*)', g or '')
    return (int(m[1]), m[2].strip()) if m else (10**9, g or '￿')


def autographs(cache, only=None, all_unlinked=False):
    """Quartet holdings RISM calls an autograph and links no scan for, straight from
    the cached MARC. 593 $a names the autograph; $3 ties it to one holding."""
    out = []
    for f in sorted(cache.glob('*.xml')):
        try:
            rec = ET.parse(f).getroot()
        except Exception:
            continue
        if not (by_composer(rec) and is_quartet(rec)): continue
        sid = f.stem
        hold = {h.get('3') or f'_{i}': h for i, h in enumerate(fields(rec, '852'))}
        # A digitization link, and which holding it belongs to.
        dig = {d.get('3') for d in fields(rec, '856')
               if 'IIIF' in d.get('x', '') or d.get('x') == 'Digitized'
               or d.get('q', '').startswith('image/')}
        types = {}
        for d in fields(rec, '593'):
            if d.get('a'): types.setdefault(d.get('3'), d['a'])
        ut = (fields(rec, '240') or [{}])[0]
        cat = fields(rec, '690')
        g = next((c.get('n') for c in cat
                  if c.get('0') == 'publications/29' or re.search(r'\bgerb\b', c.get('a', ''), re.I)), None)
        for hid, h in hold.items():
            if hid in dig: continue
            if len(hold) == 1 and dig: continue
            t = types.get(hid) or (next(iter(types.values())) if len(types) == 1 else '')
            if not all_unlinked and 'utograph' not in t: continue
            if only and h.get('a') not in only: continue
            out.append(dict(siglum=h.get('a'), institution=h.get('e'), shelfmark=h.get('c'),
                            institution_id=h.get('x'), source_type=t, gerard=g,
                            title=ut.get('a') or (fields(rec, '245') or [{}])[0].get('a'),
                            scoring=ut.get('m'), source_id=sid,
                            source=f'{BASE}/sources/{sid}'))
    out.sort(key=lambda r: (r['siglum'] or '', gnum(r['gerard'])))
    return out


# --- Gallica -----------------------------------------------------------------

def classify(title, source):
    """(form, medium, strings) from Gallica's free text. Titles are the only evidence."""
    t = f'{title} {source}'
    form = ('quintet' if QUINTET.search(t) else 'trio' if TRIO.search(t) else
            'quartet' if FOUR_PART.search(t) else
            'quartet?' if WEAK_FORM.search(t) and FOUR_STRINGS.search(t) else 'other')
    medium = ('autograph' if AUTOGRAPH.search(t) else
              'manuscript' if MANUSCRIPT.search(t) else 'print')
    # Only a *named* wind or keyboard part rules a four-part work out. Requiring the title
    # to name violins instead threw away three of the Opéra autographs -- 'Quartetti de
    # Boccherini' and 'Mese di Giugno. 1794. Quartettino' simply do not state their scoring.
    arrangement = bool(NOT_STRINGS.search(t))
    return form, medium, not arrangement


def sru(query, start, rows=50):
    url = 'https://gallica.bnf.fr/SRU?' + urlencode(
        {'operation': 'searchRetrieve', 'version': '1.2', 'query': query,
         'maximumRecords': rows, 'startRecord': start})
    return ET.fromstring(fetch(url, 'application/xml'))


def parse(root):
    out = []
    for rec in root.findall('.//srw:record', SRW):
        d = {}
        for e in rec.iter():
            t = e.tag.split('}')[-1]
            if t in ('title', 'identifier', 'source', 'date') and e.text:
                d.setdefault(t, []).append(e.text.strip())
        ark = next((i for i in d.get('identifier', []) if 'ark:' in i), '')
        if not ark: continue
        title = (d.get('title') or [''])[0]
        src = (d.get('source') or [''])[0]
        m = re.search(r'(ark:/\d+/\w+)', ark)
        # dc:source ends in the shelfmark, and for the Opéra autographs it is more precise
        # than RISM's: 'RES-507 (14)' against RISM's uniform 'RES-507 (2)' for all seven.
        sm = re.search(r'([A-Z][A-Za-z0-9-]*[- ]?\d[\w.\-/ ]*(?:\(\d[\d,]*\))?)\s*$', src)
        form, medium, strings = classify(title, src)
        out.append(dict(title=title, ark=ark, source=src, date=(d.get('date') or [''])[0],
                        shelfmark=sm[1].strip() if sm else None,
                        manifest=f'https://gallica.bnf.fr/iiif/{m[1]}/manifest.json' if m else None,
                        form=form, medium=medium, strings=strings,
                        autograph=medium == 'autograph'))
    return out


def gallica_all(query, cap=400, rows=50):
    """Every BnF-music hit for one query, paginated.

    `maximumRecords` alone is a recall trap: 'Boccherini' matches 2515 records and one page
    of 50 was all the first version of this ever saw. Worse, Gallica has the same fault as
    RISM -- a page in the middle comes back with zero records and no error, so a single walk
    silently skips 50 records. Each empty page is retried once before it is believed."""
    found, start, total = {}, 1, None
    while start <= cap:
        try:
            root = sru(query, start, rows)
        except Exception as e:
            print(f'  ! "{query}" @{start}: {e}', file=sys.stderr)
            break
        if total is None:
            total = int(root.findtext('.//srw:numberOfRecords', namespaces=SRW) or 0)
        recs = parse(root)
        if not recs:
            time.sleep(1)
            try:
                recs = parse(sru(query, start, rows))       # the empty-page retry
            except Exception:
                recs = []
            if not recs: print(f'  . "{query}" @{start}: empty twice, skipping',
                               file=sys.stderr)
        for r in recs:
            if BNF_DEPT.search(r['source']): found.setdefault(r['ark'], r)
        start += rows
        if total and start > total: break
        time.sleep(.3)
    return found, total


def canvases(manifest_bytes):
    d = json.loads(manifest_bytes)
    s = d.get('sequences')
    cs = (s[0].get('canvases', []) if s else d.get('items', []))
    out = []
    for c in cs:
        im = (c.get('images') or [{}])[0].get('resource', {})
        svc = im.get('service') or {}
        if isinstance(svc, list): svc = svc[0] if svc else {}
        out.append((svc.get('@id') or svc.get('id'), im.get('@id')))
    return out


def grab(hit, outdir, limit=0):
    """Fetch a Gallica hit's pages. Existing files are skipped, so re-runs resume."""
    d = outdir / re.sub(r'[^\w.-]', '_', hit['ark'].split('/')[-1])
    d.mkdir(parents=True, exist_ok=True)
    mf = d / 'manifest.json'
    if not mf.exists(): mf.write_bytes(fetch(hit['manifest'], 'application/json'))
    cs = canvases(mf.read_bytes())
    # A machine-readable sidecar beside the readable one, so a page builder does not have
    # to parse prose back out of FOUND.md.
    (d / 'metadata.json').write_text(json.dumps(
        dict(source='gallica', ark=hit['ark'], title=hit['title'],
             shelfmark=hit.get('shelfmark'), institution=hit['source'],
             siglum=None, medium=hit['medium'], form=hit['form'],
             strings=hit['strings'], is_autograph=hit['autograph'],
             date=hit.get('date'), manifest=hit['manifest'], pages=len(cs)),
        ensure_ascii=False, indent=1))
    (d / 'FOUND.md').write_text(
        f"# {hit['title']}\n\n"
        f"Found by searching Gallica, **not** linked from RISM.\n\n"
        f"- **Gallica:** <{hit['ark']}>\n- **Held by:** {hit['source']}\n"
        f"- **Shelfmark (Gallica):** {hit.get('shelfmark') or 'not parsed'}\n"
        f"- **Medium (from Gallica's title):** {hit['medium']}\n"
        f"- **Form:** {hit['form']}{'' if hit['strings'] else ' — arrangement, not strings'}\n"
        f"- **IIIF manifest:** <{hit['manifest']}>\n- **Pages:** {len(cs)}\n\n"
        "Identification against a Gérard number is still a human job, but Gallica's shelfmark\n"
        "gives the volume within RES-507, which RISM does not -- it lists all seven as\n"
        "'RES-507 (2)'. That plus Boccherini's own month-and-year dating should settle it.\n")
    n = 0
    print(f"{d.name}: {len(cs)} pages — {hit['title'][:56]}", file=sys.stderr)
    for i, (svc, direct) in enumerate(cs, 1):
        if limit and i > limit: break
        f = d / f'{i:03d}.jpg'
        if f.exists() and f.stat().st_size: continue
        try:
            f.write_bytes(fetch(f'{svc}/full/max/0/default.jpg' if svc else direct, 'image/jpeg'))
            n += 1
        except Exception as e:
            print(f'  ! page {i}: {e}', file=sys.stderr)
        time.sleep(.2)
    return n, len(cs)


def report(rows, hits, outdir, fetched, grab_list):
    """GALLICA-SEARCH.md: every BnF-music Boccherini hit, classified, with deep links."""
    bnf = hits.get('BnF', [])
    L = ['# Scans at libraries RISM does not link — BnF / Gallica',
         '', 'RISM links a digitization for about 5% of the quartet holdings it catalogues.',
         'Gallica is the one portal among the holding libraries with a real search API, and',
         'it covers every BnF-family siglum at once: **F-Pn, F-Pc, F-Po, F-Pmeyer,',
         'F-Prothschild**. Hits are attributed to a BnF *department*, which is as precise as',
         "Gallica's metadata allows.", '']
    if bnf:
        c = collections.Counter((h['form'], h['medium']) for h in bnf)
        L += [f'{len(bnf)} Boccherini items in the BnF music departments:', '',
              '| form | autograph | manuscript | print |', '|---|---:|---:|---:|']
        for f_ in ('quartet', 'quintet', 'trio', 'other'):
            if not any(k[0] == f_ for k in c): continue
            L.append(f"| {f_} | {c[(f_, 'autograph')] or '—'} | {c[(f_, 'manuscript')] or '—'} "
                     f"| {c[(f_, 'print')] or '—'} |")
        L += ['', 'Form and medium are read off Gallica\'s free-text titles, so treat them as',
              "strong hints, not facts. 'Divertimenti' is one of Boccherini's own words for",
              'these quartets, which is why it counts as four-part here.', '']
        arr = [h for h in bnf if h['form'].startswith('quartet') and not h['strings']]
        if arr:
            L += [f'{len(arr)} four-part items are **arrangements**, not string quartets —',
                  'their titles name flute, clarinet, horn, bassoon or keyboard. Excluded from',
                  'downloads unless you pass `--arrangements`.', '']
        order = {'autograph': 0, 'manuscript': 1, 'print': 2}
        for f_, head, note in (
            ('quartet', 'String quartets',
             'Titles name four parts outright, or use one of Boccherini\'s own words for a '
             'quartet (Quartettino, Divertimenti).'),
            ('quartet?', 'Probably quartets — verify',
             "Titled *Sonata* or *Sinfonia* but spelling out four string parts. RISM files 7 "
             'of these quartets under the uniform title "Sonatas", so they are worth having; '
             'the form is an inference from the title, not a fact.')):
            sq = sorted((h for h in bnf if h['form'] == f_ and h['strings']),
                        key=lambda h: (order.get(h['medium'], 9), h['shelfmark'] or ''))
            if not sq: continue
            L += ['---', '', f'## {head} ({len(sq)})', '', note, '',
                  'Sorted autograph first, then manuscript, then print. `pages` is what is on disk.', '',
                  '| title | shelfmark | medium | date | pages | link |',
                  '|---|---|---|---|---|---|']
            for h in sq:
                L.append(f"| {h['title'][:54].replace('|', chr(92) + '|')} "
                         f"| {(h['shelfmark'] or '—').replace('|', chr(92) + '|')} "
                         f"| {'**AUTOGRAPH**' if h['autograph'] else h['medium']} "
                         f"| {h['date'] or '—'} "
                         f"| {fetched.get(h['ark'], ('', ''))[1] or ('queued' if h in grab_list else '—')} "
                         f"| [{h['ark'].split('/')[-1]}]({h['ark']}) |")
            L.append('')
        for f_, head in (('quintet', 'Quintets and larger'), ('trio', 'Trios'),
                         ('other', 'Unclassified')):
            g = [h for h in bnf if h['form'] == f_]
            if not g: continue
            L += [f'## {head} ({len(g)})', '',
                  'Not quartets; listed so nothing found is silently dropped.', '',
                  '| title | shelfmark | medium | link |', '|---|---|---|---|']
            for h in sorted(g, key=lambda h: h['shelfmark'] or ''):
                L.append(f"| {h['title'][:54].replace('|', chr(92) + '|')} "
                         f"| {(h['shelfmark'] or '—').replace('|', chr(92) + '|')} "
                         f"| {h['medium']} | [{h['ark'].split('/')[-1]}]({h['ark']}) |")
            L.append('')
    L += ['---', '', '## What RISM says these libraries hold, unscanned', '']
    for sig in sorted({r['siglum'] for r in rows}):
        mine = [r for r in rows if r['siglum'] == sig]
        if sig not in BNF_SIGLA and sig not in NO_API: continue
        L += [f'### {sig} — {mine[0]["institution"] or ""} ({len(mine)})', '']
        iid = mine[0]['institution_id']
        if iid: L += [f'RISM library page: <{BASE}/{iid}>', '']
        if sig in NO_API:
            L += [f'**Not searchable from a script.** {NO_API[sig]}', '']
        L += ['| G | shelfmark | type | title | source |', '|---|---|---|---|---|']
        for r in sorted(mine, key=lambda r: gnum(r['gerard'])):
            L.append(f"| {r['gerard'] or '—'} "
                     f"| {(r['shelfmark'] or '—').replace('|', chr(92) + '|')} "
                     f"| {r['source_type'] or '—'} | {(r['title'] or '')[:24]} "
                     f"| [{r['source_id']}]({r['source']}) |")
        L.append('')
    (outdir / 'GALLICA-SEARCH.md').write_text('\n'.join(L))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=Path('.rism-cache'))
    p.add_argument('--out', type=Path, default=Path('digitizations'))
    p.add_argument('--siglum', action='append', help='only these libraries; repeatable')
    p.add_argument('--autographs-only', action='store_true',
                   help='only the holdings RISM marks Autograph manuscript')
    p.add_argument('--download', action='store_true', help='fetch the string-quartet hits')
    p.add_argument('--include', action='append',
                   choices=('quartet', 'quartet?', 'quintet', 'trio', 'other'),
                   help="forms to download; default 'quartet' and 'quartet?'")
    p.add_argument('--arrangements', action='store_true',
                   help='also download wind/keyboard arrangements')
    p.add_argument('--cap', type=int, default=400, help='max SRU records to walk per query')
    p.add_argument('--pages', type=int, default=0, help='cap pages per item (0 = all)')
    a = p.parse_args()

    rows = autographs(a.cache, set(a.siglum) if a.siglum else None, not a.autographs_only)
    sigla = {r['siglum'] for r in rows}
    print(f'{len(rows)} unlinked {"autograph " if a.autographs_only else ""}holdings '
          f'at {len(sigla)} libraries', file=sys.stderr)

    # Gallica covers every BnF-family siglum at once, so search it once rather than per
    # siglum -- the department, not the siglum, is what a hit can be attributed to.
    hits, fetched = {}, {}
    if sigla & BNF_SIGLA:
        found = {}
        for q in QUERIES:
            got, total = gallica_all(f'gallica all "{q}"', a.cap)
            new_ = [k for k in got if k not in found]
            found |= got
            print(f'  gallica "{q}": {total} records, {len(got)} in BnF music, '
                  f'{len(new_)} new (running total {len(found)})', file=sys.stderr)
        hits['BnF'] = list(found.values())
        c = collections.Counter((h['form'], h['medium']) for h in found.values())
        for (f_, m_), n in sorted(c.items()): print(f'    {n:4} {f_:8} {m_}', file=sys.stderr)
    for sig in sorted(sigla - BNF_SIGLA):
        print(f'  {sig}: {NO_API.get(sig, "no portal configured")}', file=sys.stderr)

    want = set(a.include or ['quartet', 'quartet?'])
    grab_list = [h for h in hits.get('BnF', [])
                 if h['form'] in want and h['manifest']
                 and (a.arrangements or h['strings'])]
    print(f'{len(grab_list)} items to fetch '
          f'({sum(h["autograph"] for h in grab_list)} autograph, '
          f'{sum(h["medium"] == "manuscript" for h in grab_list)} manuscript)', file=sys.stderr)
    if a.download:
        for h in grab_list:
            try:
                fetched[h['ark']] = grab(h, a.out / 'found' / 'BnF', a.pages)
            except Exception as e:
                print(f"  ! {h['ark']}: {e}", file=sys.stderr)
        print(f'downloaded {sum(v[0] for v in fetched.values())} new pages', file=sys.stderr)

    a.out.mkdir(parents=True, exist_ok=True)
    report(rows, hits, a.out, fetched, grab_list)
    print(f'-> {a.out}/GALLICA-SEARCH.md', file=sys.stderr)
