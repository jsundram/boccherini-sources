# /// script
# requires-python = ">=3.11"
# ///
"""Boccherini string-quartet incipits (Plaine & Easie) from RISM Online -> JSONL.

uv run tools/rism_incipits.py > boccherini_quartets.jsonl
uv run tools/rism_incipits.py --q '' --all     # every Boccherini source with incipits, no quartet filter
"""
import argparse, json, re, sys, time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://rism.online'
M = '{http://www.loc.gov/MARC21/slim}'
# RISM spells the same quartet several ways. The bass is 'vlc', 'b' or 'bc'; the inner
# voice is 'vla', 't-vla', 'a-vla', 'violetta' or 'taille'; the violins are 'vl (2)' or
# '2 vl'. Matching only 'vl (2), vla, vlc' silently drops the 71 sources scored
# 'vl (2), vla, b' and every incipit in them. Keyboard reductions ('cemb (2)') and
# flute or piano quartets are deliberately out.
QUARTET = re.compile(r'^(?:vl \(2\)|2 vl)\s*,\s*(?:[at]-)?(?:vla|violetta|taille)'
                     r'\s*,\s*(?:vlc|bc|b)$', re.I)
# Only consulted when a record gives no scoring at all. RISM's cataloguers write the
# uniform title in whichever language they work in -- 'Quatuors' outnumbers 'Quartets'
# two to one among the scoring-less records -- so matching only the English form silently
# dropped every BnF manuscript, including ten F-Po autographs.
TITLE_Q = re.compile(r'^\s*\d*\s*(?:quartet|quatuor|quartett)', re.I)

# A title that names a single movement is an extract, not a quartet. Dropped on the title
# fallback -- unless the source is an autograph, where a leaf in Boccherini's hand is worth
# having on its own terms.
MOVEMENT = re.compile(r'^\s*(?:\d+\.?o?\s*)?(?:tempo|minuet|menuet|larghetto|adagio|'
                      r'andantin|andante|allegrett|allegro|rond|finale|presto|grave|largo)',
                      re.I)

# Some cataloguers put the Gerard number in the title text -- '2. quartetto in mi b magg.
# [G 243]' -- rather than in a 690. It is the same evidence, so it counts the same.
G_IN_TITLE = re.compile(r'\[\s*G\.?\s*(\d+)', re.I)
# RISM cites Gérard's Boccherini catalogue by the siglum 'GerB' (690 $a), linked to
# publications/29 ('Thematic, bibliographical and critical catalogue ... Luigi Boccherini').
GERARD_PUB = 'publications/29'
GERARD = re.compile(r'\bgerb\b|g[ée]rard', re.I)
PAE = (('clef', 'g'), ('keysig', 'n'), ('timesig', 'o'), ('data', 'p'))


def get(url, accept='application/ld+json', tries=4):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers={'Accept': accept, 'User-Agent': 'boccherini-incipits/0.1'}), timeout=60) as r:
                return r.read()
        except Exception:
            if i == tries - 1: raise
            time.sleep(2 ** i)


def person(name):
    d = json.loads(get(f'{BASE}/search?' + urlencode({'mode': 'people', 'q': name})))
    return next(i['id'].rsplit('/', 1)[1] for i in d['items'] if name in json.dumps(i, ensure_ascii=False))


def _page_through(start):
    """One pass over a paginated result. (ids, totalItems)."""
    ids, total, url = [], None, start
    while url:
        d = json.loads(get(url))
        if total is None: total = d.get('totalItems')
        ids += [i['id'].rsplit('/', 1)[1] for i in d.get('items', [])]
        n = d.get('view', {}).get('next')
        url = n.get('id') if isinstance(n, dict) else n
    return ids, total


def sources(pid, q, passes=6):
    """Every source id for a person, checked against `totalItems`.

    One pass is not reliable. RISM intermittently serves a page with no `view.next`, which
    ends the walk early and silently -- repeated runs of the same query returned 613, 462
    and 528 ids. Nothing errors; you just harvest less than exists, and a different amount
    each time. So compare each pass against `totalItems` and union further passes until the
    count is reached."""
    p = {'fq': 'has-incipits:true', 'rows': 100} | ({'q': q} if q else {})
    start = f'{BASE}/people/{pid}/sources?' + urlencode(p)
    seen, total = {}, None
    for i in range(passes):
        ids, t = _page_through(start)
        if total is None: total = t
        seen |= dict.fromkeys(ids)
        if total is None or len(seen) >= total: break
        print(f'  pass {i + 1}: {len(seen)}/{total} sources; re-walking', file=sys.stderr)
        time.sleep(1)
    if total and len(seen) < total:
        print(f'WARNING: {len(seen)} of {total} sources after {passes} passes', file=sys.stderr)
    return list(seen)


def fields(rec, tag):
    return [{s.get('code'): s.text or '' for s in df.iter(M + 'subfield')}
            for df in rec.iter(M + 'datafield') if df.get('tag') == tag]


def marc(sid, cache):
    f = cache / f'{sid}.xml'
    if not f.exists():
        f.write_bytes(get(f'{BASE}/sources/{sid}', 'application/marcxml+xml'))
        time.sleep(.25)
    return ET.parse(f).getroot()


def by_composer(rec, pid):
    """Is this person the *composer*, or just someone RISM relates the source to?

    A person's `/sources` endpoint returns everything they are linked to, in any role. All
    thirteen Pleyel quartet prints in this corpus name Boccherini in a 700 with relator
    `$4 dte` -- dedicatee -- because Pleyel dedicated his Op. 9 to him. They carried 22
    Pleyel incipits into the Boccherini corpus before this check existed. MARC 100 is the
    composer, so a 100 pointing at anyone else settles it."""
    m = (fields(rec, '100') or [{}])[0]
    return not m or m.get('0') in (None, '', f'people/{pid}')


def is_quartet(rec):
    """Scoring decides. 240 $m is the uniform-title scoring; 594 $a is RISM's own reading of
    the parts and is present when 240 $m is not. Only a record with neither falls back to its
    title, so a 'Quartets' record for two harpsichords is not mistaken for one."""
    ut = (fields(rec, '240') or [{}])[0]
    sc = (ut.get('m') or (fields(rec, '594') or [{}])[0].get('a') or '').strip()
    if sc: return bool(QUARTET.match(sc))
    title = (fields(rec, '245') or [{}])[0].get('a') or ''
    if not TITLE_Q.match(ut.get('a') or title): return False
    # An autograph in Boccherini's hand is kept whatever else the record lacks.
    if any('utograph' in (d.get('a') or '') for d in fields(rec, '593')): return True
    if not (any(is_gerard(c) and c.get('n') for c in fields(rec, '690'))
            or G_IN_TITLE.search(title)):
        return False
    return not MOVEMENT.match(title)


def rows(sid, cache, everything, pid):
    try:
        r = marc(sid, cache)
    except Exception as e:
        print(f'skip {sid}: {e}', file=sys.stderr)
        return []
    if not by_composer(r, pid): return []          # Boccherini as dedicatee, not composer
    if not (everything or is_quartet(r)): return []
    ut = (fields(r, '240') or [{}])[0]
    cat = fields(r, '690')
    base = dict(
        source=f'{BASE}/sources/{sid}',
        title=ut.get('a') or (fields(r, '245') or [{}])[0].get('a'),
        key=ut.get('r'), scoring=ut.get('m'),
        gerard=next((c.get('n') for c in cat if is_gerard(c)), None),
        catalogs=[f"{c.get('a', '')} {c.get('n', '')}".strip() for c in cat],
        siglum=' '.join(filter(None, (h.get('a') for h in fields(r, '852')))))
    return [base | dict(mvt='.'.join(i.get(k, '') for k in 'abc'), caption=i.get('d'), part=i.get('m'), text=i.get('t'),
                        **{k: i.get(c) for k, c in PAE}, pae='\n'.join(f'@{k}:{i[c]}' for k, c in PAE if i.get(c)))
            for i in fields(r, '031') if i.get('p')]


def is_gerard(c):
    return c.get('0') == GERARD_PUB or bool(GERARD.search(c.get('a', '')))


def gnum(g):
    """Sort key for a Gérard number: '195' < '206/3' < 'deest' < missing."""
    m = re.match(r'\s*(\d+)(.*)', g or '')
    return (int(m[1]), m[2].strip()) if m else (10**9, g or '\uffff')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--name', default='Boccherini, Luigi')
    p.add_argument('--person', help='RISM person id; skips name lookup')
    p.add_argument('--q', default='Quartets', help="server-side keyword prefilter; '' to disable")
    p.add_argument('--all', action='store_true', help='skip local quartet filter')
    p.add_argument('--cache', type=Path, default=Path('.rism-cache'))
    p.add_argument('-j', type=int, default=4)
    a = p.parse_args()
    a.cache.mkdir(exist_ok=True)
    pid = a.person or person(a.name)
    ids = sources(pid, a.q)
    print(f'person {pid}: {len(ids)} sources with incipits', file=sys.stderr)
    with ThreadPoolExecutor(a.j) as ex:
        out = [r for rs in ex.map(lambda s: rows(s, a.cache, a.all, pid), ids) for r in rs]
    out.sort(key=lambda r: (gnum(r['gerard']), r['source'], r['mvt']))
    for r in out: print(json.dumps(r, ensure_ascii=False))
    gs = {r['gerard'] for r in out} - {None}
    print(f"{len(out)} incipits, {len(gs)} Gérard numbers, {sum(not r['gerard'] for r in out)} without G", file=sys.stderr)
