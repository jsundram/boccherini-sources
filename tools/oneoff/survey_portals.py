# /// script
# requires-python = ">=3.11"
# ///
"""Can each holding library be searched by a script? One row per library, with evidence.

    uv run tools/oneoff/survey_portals.py                 # survey every library, write the report
    uv run tools/oneoff/survey_portals.py --siglum I-Nc   # just one
    uv run tools/oneoff/survey_portals.py --no-probe      # report from cache only, no network

RISM links a scan for about 5% of the quartet holdings it catalogues. The other 95%
sit at 169 libraries, and the honest question is which of those can be searched
automatically and which need a person. This answers that per library rather than
leaving it as "portals are inconsistent".

For each library it collects:

  * how many unlinked quartet holdings RISM records there
  * the library's own website, from its RISM institution record (RISM does carry it)
  * every host RISM already links for that library, taken from the MARC 856 fields --
    catalogue links as well as digitizations, because a catalogue host is exactly
    where an API would live
  * whether OAI-PMH or SRU answers at any of those hosts

Writes `digitizations/PORTAL-SURVEY.md`, ordered by holdings, and caches every probe
in `.rism-cache/portals.json` so a re-run costs nothing.

### What a verdict means

  api        OAI-PMH or SRU answered. Scriptable; worth writing a resolver for.
  known      Verified by hand this session -- see KNOWN below. Includes portals that
             work (Gallica) and portals that actively refuse automation.
  website    RISM gives a website but no API answered. A person can search it.
  no url     RISM records no website and links no host. Start from the RISM library
             page, which lists the holdings.

A negative is weaker evidence than a positive: OAI and SRU are only two of the ways
a library might be queryable, and a site can hide one behind an unguessable path. So
`website` means "not found at the usual endpoints", not "definitely impossible".
"""
import argparse, collections, json, re, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request, urlopen

BASE = 'https://rism.online'
BOCCHERINI = 'people/30000391'
M = '{http://www.loc.gov/MARC21/slim}'
BROWSER = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')
QUARTET = re.compile(r'^(?:vl \(2\)|2 vl)\s*,\s*(?:[at]-)?(?:vla|violetta|taille)'
                     r'\s*,\s*(?:vlc|bc|b)$', re.I)
TITLE_Q = re.compile(r'^\s*\d*\s*quartet', re.I)
# Hosts that are never the holding library's own catalogue.
IGNORE_HOST = re.compile(r'wasserzeichen-online|hdl\.handle\.net|nbn-resolving|'
                         r'doi\.org|viaf\.org|d-nb\.info|wikidata\.org|worldcat\.org', re.I)

# Established by hand in this session. Recorded because a probe cannot see any of it:
# an SRU endpoint at a path no guess would find, or a server that answers a browser
# and refuses everything else.
KNOWN = {
    'S-Sm': ('known', 'SEARCHED, DEAD END. Discovery runs through Alvin, which returns the same '
                      'items already found via S-Skma. Its own archive interface '
                      '(arkiv.musikochteaterbiblioteket.se) is Swedish-language, hard to drive, and '
                      'returns nothing for Boccherini. Sweden as a whole is exhausted: S-Skma had 4 '
                      'digitized of 34 holdings and S-Sm adds nothing.'),
    'GB-Lam': ('known', 'SEARCHED, DEAD END. Royal Academy of Music runs Koha at `lib.ram.ac.uk` '
                        '(`/cgi-bin/koha/opac-search.pl?idx=au&q=boccherini`) -- a catalogue with no '
                        'digital copies attached, the same picture as B-Bc. Koha instances in this '
                        'survey have produced nothing: they index holdings, they do not serve images.'),
    'NL-Uim': ('known', 'SEARCHED, DEAD END. Utrecht routes discovery through WorldCat, which mostly '
                        'returns other libraries\' holdings; their own digitized Boccherini is a '
                        'single minuet. The 31 RISM holdings are catalogue records. RISM links a '
                        'FAUST database (dmga.faust-hosting.de) and WorldCat for this siglum, '
                        'neither of which serves images. The library itself has no digital-collections '
                        'search: uu.nl/en/university-library/searching-for-literature/search-engines '
                        'lists third-party engines instead, which is why a search returns other '
                        'libraries\' copies.'),
    'B-Bc': ('known', 'SEARCHED, DEAD END. The Conservatoire runs a Koha catalogue at '
                      '`catalog.b-bc.org` (e.g. `/cgi-bin/koha/opac-search.pl?q=an:57075`), which '
                      'is a catalogue only -- no digitized music behind it. Its 44 RISM holdings '
                      'are records, not scans.'),
    'F-Po': ('known', 'Gallica SRU at `gallica.bnf.fr/SRU`, verified: 339 Boccherini items in '
                      'the BnF music departments, 37 string quartets. Covers every F-P* siglum.'),
    'F-Pn': ('known', 'Same Gallica SRU as F-Po — one search covers all BnF departments.'),
    'F-Pc': ('known', 'Same Gallica SRU as F-Po.'),
    'F-Pmeyer': ('known', 'Same Gallica SRU as F-Po.'),
    'F-Prothschild': ('known', 'Same Gallica SRU as F-Po.'),
    'D-MÜs': ('known', 'Visual Library OAI-PMH answers at `sammlungen.ulb.uni-muenster.de/oai/`, '
                       'but OAI has no keyword search — you can only walk sets. No search '
                       'endpoint found, so the Santini autograph needs a manual look.'),
    'D-Bhm': ('known', 'No IIIF or searchable digital collection found for the Universität der '
                       'Künste. Manual.'),
    'D-Dl': ('known', 'SLUB Dresden publishes IIIF (`iiif.slub-dresden.de`, images on '
                      '`images.iiif.slub-dresden.de`) and one of its items was downloaded this '
                      'way, but its catalogue endpoints refused scripted requests.'),
    'D-F': ('known', 'SEARCHED, DEAD END for string quartets. Visual Library OAI answers at '
                     '`sammlungen.ub.uni-frankfurt.de/oai/` (walkable, no keyword search) and the '
                     'site is behind the same Anubis browser check as Eichstaett. The one item '
                     'musiconn surfaced, urn:nbn:de:hebis:30-1160725 = Mus.pr.Q 51/41, turns out '
                     'to be FLUTE quartets -- an arrangement, not the string quartets. Frankfurt '
                     'shelfmarks read as quartets either way, so check the scoring before fetching.'),
    'GB-Lbl': ('known', 'British Library search endpoints did not respond to scripted requests. '
                        'Manual.'),
    'DK-Km': ('known', '`kb.dk` returned 403 to a scripted request. Manual.'),
    'I-Nc': ('known', 'SEARCHED, EXHAUSTED. Internet Culturale holds some digitized Boccherini but '
                      'no quartet parts. `opac.sbn.it` serves HTML only, and RISM already links its '
                      '`id.sbn.it` records — which are catalogue entries, not scans. The 52 holdings '
                      'here are catalogue entries; nothing to fetch.'),
    'I-Vc': ('known', 'Same Italian picture as I-Nc: SBN catalogue records, no digitized quartet parts.'),
    'I-Fn': ('known', 'Same Italian picture as I-Nc.'),
    'E-Mn': ('known', 'Cloudflare. Every BNE host refuses the TLS handshake to a scripted client, '
                      'and `curl` from an unblocked machine still gets a challenge page rather than '
                      'results -- only a browser gets through. A saved results page yielded 14 '
                      'quartet prints; see BNE-TODO.md.'),
    'D-Mbs': ('known', 'SEARCHED, EXHAUSTED. BSB digitizes heavily and its delivery API is scriptable '
                       '(api.digitale-sammlungen.de), but its manuscript portal holds only two '
                       'Boccherini items and both are quintets (e.g. bsb00112249, GerB 380). Its 34 '
                       'RISM holdings are catalogue entries, not scans. Not worth a second look.'),
    'S-Skma': ('known', 'SEARCHED, NEARLY EXHAUSTED. Search and record pages both return 403 to a '
                        'script. Of 34 RISM holdings only 4 are digitized; W 4-R was downloaded by '
                        'hand and turned out to be the Hummel print, not the manuscript both it and '
                        'RISM call it.'),
    'CZ-Pu': ('known', 'Manuscriptorium needs a portal session before it serves images.'),
    'US-CAe': ('known', "Harvard's IIIF link in RISM is broken — the DRS id 404s and the redirect "
                        'chain ends at a manifest for a different work. Search Harvard by shelfmark.'),
    'US-R': ('known', 'Sibley/Rochester resolves through the Handle REST API to '
                      '`urresearch.rochester.edu`, whose pages carry per-part PDFs. Already '
                      'harvested by `rism_digitizations.py`.'),
}

# Worth knowing even though it is not a holding library: RISM's own cataloguing platform
# exposes SRU at `muscat.rism.info/sru`, and it rejects version=1.2 with 'Unsupported
# version' -- it wants **1.1**. 320 records for 'Boccherini'. Fewer than rism.online's JSON
# API returns, so it is a curiosity here rather than a better source.

# Endpoint shapes worth trying. Two families, a handful of conventional paths each.
# Yield is low by design limits: of the first 21 hosts probed, exactly one answered. A
# library's public website is rarely its catalogue server, and the catalogue usually lives
# on a subdomain no convention predicts. Read a `website` verdict accordingly.
PROBES = (('oai', '/oai?verb=Identify'), ('oai', '/oai/?verb=Identify'),
          ('oai', '/oai2?verb=Identify'), ('oai', '/cgi-bin/oai?verb=Identify'),
          ('sru', '/sru?operation=explain&version=1.2'),
          ('sru', '/SRU?operation=explain&version=1.2'))


def fields(rec, tag):
    return [{s.get('code'): s.text or '' for s in df.iter(M + 'subfield')}
            for df in rec.iter(M + 'datafield') if df.get('tag') == tag]


def by_composer(rec):
    """MARC 100 is the composer; a 100 naming anyone else means the source is not his."""
    m = (fields(rec, '100') or [{}])[0]
    return not m or m.get('0') in (None, '', BOCCHERINI)


def is_quartet(rec):
    ut = (fields(rec, '240') or [{}])[0]
    sc = (ut.get('m') or (fields(rec, '594') or [{}])[0].get('a') or '').strip()
    if sc: return bool(QUARTET.match(sc))
    return bool(TITLE_Q.match(ut.get('a') or (fields(rec, '245') or [{}])[0].get('a') or ''))


def survey_corpus(cache):
    """{siglum: {holdings, institution, institution_id, hosts}} for unlinked quartet holdings."""
    out = {}
    for f in sorted(cache.glob('*.xml')):
        try:
            rec = ET.parse(f).getroot()
        except Exception:
            continue
        if not (by_composer(rec) and is_quartet(rec)): continue
        hold = {h.get('3') or f'_{i}': h for i, h in enumerate(fields(rec, '852'))}
        dig = {d.get('3') for d in fields(rec, '856')
               if 'IIIF' in d.get('x', '') or d.get('x') == 'Digitized'
               or d.get('q', '').startswith('image/')}
        # Every host RISM links for a holding, digitization or catalogue alike.
        hosts = collections.defaultdict(set)
        for d in fields(rec, '856'):
            if not d.get('u'): continue
            sig = hold.get(d.get('3'), {}).get('a') or (
                next(iter(hold.values()), {}).get('a') if len(hold) == 1 else None)
            h = re.sub(r'^https?://([^/]+).*', r'\1', d['u']).lower()
            if sig and not IGNORE_HOST.search(h): hosts[sig].add(h)
        for hid, h in hold.items():
            sig = h.get('a')
            if not sig: continue
            e = out.setdefault(sig, dict(siglum=sig, institution=h.get('e'),
                                         institution_id=h.get('x'), holdings=0, hosts=set()))
            e['hosts'] |= hosts.get(sig, set())
            if hid in dig: continue
            if len(hold) == 1 and dig: continue
            e['holdings'] += 1
    return {k: v for k, v in out.items() if v['holdings']}


def get(url, accept='*/*', tries=2, timeout=25):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers={'Accept': accept, 'User-Agent': BROWSER}),
                         timeout=timeout) as r:
                return r.read(), r.status
        except Exception as e:
            if i == tries - 1: return None, str(e)
            time.sleep(1)


def inst_record(iid, cache):
    """RISM institution record, cached. It carries the library's own website."""
    d = cache / 'institutions'
    d.mkdir(exist_ok=True)
    f = d / f"{iid.rsplit('/', 1)[1]}.json"
    if not f.exists():
        body, st = get(f'{BASE}/{iid}', 'application/ld+json')
        if not body: return {}
        f.write_bytes(body)
        time.sleep(.2)
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def website(rec):
    """The library's own site, from `location.website` — the one field that holds it.

    Scraping every URL out of the record instead pulls in RISM's own boilerplate: DIAMM,
    the Cantus database and MGG Online outranked every real library when the candidate
    hosts were counted that way."""
    try:
        v = rec['location']['website']['value']
    except (KeyError, TypeError):
        return []
    urls = v if isinstance(v, list) else next(iter(v.values()), []) if isinstance(v, dict) else [v]
    out = []
    for u in (urls if isinstance(urls, list) else [urls]):
        u = str(u).strip().rstrip('.,')
        if u.startswith('http'): out.append(u)
    return out


def probe(host, cached, do_probe=True):
    """Which of OAI / SRU answer at this host. Cached across runs."""
    if host in cached: return cached[host]
    if not do_probe: return None
    res = {}
    for kind, path in PROBES:
        if kind in res: continue
        body, st = get(f'https://{host}{path}', 'text/xml')
        if not body: continue
        head = body[:2000].decode('utf8', 'replace').lower()
        if kind == 'oai' and 'oai-pmh' in head and 'identify' in head:
            res['oai'] = f'https://{host}{path}'
        if kind == 'sru' and ('explainresponse' in head or 'zeerex' in head
                              or 'searchretrieveresponse' in head):
            res['sru'] = f'https://{host}{path}'
        time.sleep(.2)
    cached[host] = res
    return res


def report(rows, outdir):
    tot = sum(r['holdings'] for r in rows)
    api = [r for r in rows if r['verdict'] == 'api']
    known = [r for r in rows if r['verdict'] == 'known']
    web = [r for r in rows if r['verdict'] == 'website']
    none = [r for r in rows if r['verdict'] == 'no url']
    L = ['# Can each holding library be searched by a script?',
         '', f'{len(rows)} libraries hold {tot} quartet holdings that RISM links no scan for.',
         'This is a verdict per library, with the evidence behind it.',
         '', '| verdict | libraries | holdings | meaning |', '|---|---:|---:|---|',
         f'| `api` | {len(api)} | {sum(r["holdings"] for r in api)} | OAI-PMH or SRU answered at a host RISM links |',
         f'| `known` | {len(known)} | {sum(r["holdings"] for r in known)} | established by hand — works, or actively refuses |',
         f'| `website` | {len(web)} | {sum(r["holdings"] for r in web)} | a site to search, no API at the usual endpoints |',
         f'| `no url` | {len(none)} | {sum(r["holdings"] for r in none)} | RISM records no website and links no host |',
         '',
         'A negative is weaker than a positive, and here it is *much* weaker. Of the hosts',
         'probed so far only a single one answered — a public website is rarely the catalogue',
         'server, and the catalogue normally sits on a subdomain no convention predicts. So',
         '`website` means "no OAI or SRU at the conventional paths on the host RISM gives",',
         'not "cannot be automated". Every `known` row, by contrast, was tried directly and',
         'says what actually happened.',
         '',
         'Probing is also incomplete: it runs inside a sandbox that requires every host to be',
         'declared in advance, and redirects keep introducing new ones. Results are cached in',
         '`.rism-cache/portals.json`, so re-running this outside the sandbox finishes the job',
         'without repeating any work.',
         '', '---', '']
    for head, group, note in (
        ('Scriptable', api + known,
         'Worth writing a resolver for — or, where the note says so, worth not trying again.'),
        ('Needs a person', web,
         'RISM gives a website; no OAI or SRU answered. Search these by hand.'),
        ('No lead but the RISM record', none,
         'Start from the RISM library page, which lists what it holds.')):
        if not group: continue
        L += [f'## {head} ({len(group)} libraries, '
              f'{sum(r["holdings"] for r in group)} holdings)', '', note, '',
              '| siglum | library | holdings | verdict | evidence |',
              '|---|---|---:|---|---|']
        for r in sorted(group, key=lambda r: -r['holdings']):
            ev = r['evidence'] or '—'
            L.append(f"| [{r['siglum']}]({BASE}/{r['institution_id']}) "
                     f"| {(r['institution'] or '')[:40].replace('|', '\\|')} "
                     f"| {r['holdings']} | `{r['verdict']}` "
                     f"| {ev.replace('|', '\\|')} |")
        L.append('')
    (outdir / 'PORTAL-SURVEY.md').write_text('\n'.join(L))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=Path('.rism-cache'))
    p.add_argument('--out', type=Path, default=Path('digitizations'))
    p.add_argument('--siglum', action='append', help='only these libraries; repeatable')
    p.add_argument('--min-holdings', type=int, default=0, help='skip libraries below this')
    p.add_argument('--no-probe', action='store_true', help='cache only, no network probing')
    a = p.parse_args()

    corpus = survey_corpus(a.cache)
    if a.siglum: corpus = {k: v for k, v in corpus.items() if k in set(a.siglum)}
    rows = [v for v in corpus.values() if v['holdings'] >= a.min_holdings]
    print(f'{len(rows)} libraries, {sum(r["holdings"] for r in rows)} unlinked holdings',
          file=sys.stderr)

    pf = a.cache / 'portals.json'
    cached = json.loads(pf.read_text()) if pf.exists() else {}
    for i, r in enumerate(sorted(rows, key=lambda r: -r['holdings']), 1):
        if r['siglum'] in KNOWN:
            r['verdict'], r['evidence'] = KNOWN[r['siglum']]
            continue
        rec = inst_record(r['institution_id'], a.cache) if r['institution_id'] else {}
        sites = website(rec)
        cands = list(r['hosts']) + [re.sub(r'^https?://([^/]+).*', r'\1', s) for s in sites]
        seen, hits = set(), {}
        for h in cands:
            h = h.lower()
            if h in seen or IGNORE_HOST.search(h): continue
            seen.add(h)
            got = probe(h, cached, not a.no_probe)
            if got: hits |= got
        if hits:
            r['verdict'] = 'api'
            r['evidence'] = ' · '.join(f'{k.upper()} `{v}`' for k, v in sorted(hits.items()))
        elif sites or r['hosts']:
            r['verdict'] = 'website'
            bits = [f'<{s}>' for s in sites[:2]] + [f'`{h}`' for h in sorted(r['hosts'])[:3]]
            r['evidence'] = 'no OAI/SRU found at ' + ', '.join(bits)
        else:
            r['verdict'] = 'no url'
            r['evidence'] = 'RISM records no website for this library'
        if i % 20 == 0:
            pf.write_text(json.dumps(cached, ensure_ascii=False, indent=1))
            print(f'  {i}/{len(rows)} …', file=sys.stderr)
    pf.write_text(json.dumps(cached, ensure_ascii=False, indent=1))

    a.out.mkdir(parents=True, exist_ok=True)
    report(rows, a.out)
    c = collections.Counter(r['verdict'] for r in rows)
    print('  ' + ', '.join(f'{v} {k}' for k, v in c.most_common()), file=sys.stderr)
    print(f'-> {a.out}/PORTAL-SURVEY.md', file=sys.stderr)
