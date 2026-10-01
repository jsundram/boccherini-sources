# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Boccherini string-quartet digitizations: inventory MARC 856, then fetch them.

    uv run tools/rism_digitizations.py                       # inventory -> stdout JSONL
    uv run tools/rism_digitizations.py --download            # fetch everything fetchable
    uv run tools/rism_digitizations.py --download --full     # ... at full resolution
    uv run tools/rism_digitizations.py --g 201 --download    # one Gerard number

Companion to `rism_incipits.py`, which harvests MARC 031 (the incipits). This
one reads MARC 856 -- electronic location -- off the same records and the same
`.rism-cache/`, so an inventory over cached sources costs no network at all.

Re-runnable: every file is skipped if it already exists, so a second run
downloads only what is missing. Delete a directory to re-fetch it.

Output tree, keyed on the Gerard number where RISM records one:

    digitizations/
      INDEX.md                     what we have, by G number
      inventory.jsonl              every 856 link, fetchable or not
      G201/990054321_D-B/
        metadata.json              the full MARC story for this source
        README.md                  the same, readable, next to the images
        manifest.json              the IIIF manifest as served, for provenance
        001.jpg ...                the pages

Sources RISM gives no Gerard number land in `unidentified/`, named by source id
and siglum, with the title and plate number in their metadata -- enough to
identify them in a second pass.

### The four kinds of 856, and which are images

  iiif       $x 'IIIF manifest (digitized source)'. A digitized book on RISM's
             own server. Downloadable page by page.
  image      $q 'image/jpeg'. Single page photos attached in Muscat.
  digitized  $x 'Digitized' -- a *landing page* at the holding library. A real
             scan sits behind it, reached by the resolvers below.
  other      $x 'Other' -- catalogue descriptions, RISM card scans, watermark
             databases, microfilm notes. Not the music; inventoried, never fetched.

### Resolvers

A `digitized` landing page is not an image. Each institution wraps its scans
differently, so each needs its own step from resolver URL to IIIF manifest:

  SBB      resolver.staatsbibliothek-berlin.de -> redirects to a `PPN=` viewer
           URL -> content.staatsbibliothek-berlin.de/dc/<PPN>/manifest
  MDZ      urn:nbn:de:bvb:12-<bsbNNNNNNNN> -> api.digitale-sammlungen.de
  Gallica  ark:/12148/<id> -> gallica.bnf.fr/iiif/.../manifest.json
  Handle   hdl.handle.net/1802/* (Sibley, Rochester) -> the Handle REST API gives
           a urresearch.rochester.edu page -> scrape its per-part PDF links.
           These arrive as PDFs named by part ('...violin1.pdf'), not images.

What cannot be fetched goes to `MANUAL-DOWNLOADS.md` with a deep link and the
reason, each established by trying it: six Eichstaett prints behind an Anubis
proof-of-work gate on `nbn-resolving.org`; one Biblioteca Nacional de Espana
source whose server never completes a TLS handshake; one Manuscriptorium record
needing a session; and one Harvard link that is simply wrong -- its DRS id 404s
and the redirect chain ends at a manifest for a different work entirely, so it is
refused rather than filed under a Gerard number it does not belong to.

Some libraries publish a valid manifest with an empty `canvases` list -- the
record and its structure, no page images. Those are reported, not left as an
empty directory.

### Resolution

RISM's own IIIF server advertises `level1` with `maxWidth/maxHeight: 1000`, so
one request never returns more than 1000px a side even though the scans are
~3500x4500. It does honour region requests, so `--full` fetches those pages as
1000px tiles and stitches them -- about 20 requests a page instead of one.
Servers that do not cap (SBB, MDZ, Gallica) return full size in one request
either way, so `--full` costs nothing there and is only expensive for RISM.
"""
import argparse, io, json, re, subprocess, sys, time
from collections import Counter
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://rism.online'
M = '{http://www.loc.gov/MARC21/slim}'
UA = 'boccherini-digitizations/0.1 (+research use; contact via RISM)'
# Some library servers reject unfamiliar agents outright (Gallica 403s, Rochester
# stalls), so third-party hosts get a browser string.
BROWSER = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')
# Same siglum handling as rism_incipits.py: RISM cites Gerard by 'GerB' (690 $a),
# linked to publications/29, not the word 'Gerard'.
GERARD_PUB = 'publications/29'
GERARD = re.compile(r'\bgerb\b|g[ée]rard', re.I)
# RISM spells the same quartet several ways. The bass is 'vlc', 'b' or 'bc'; the inner
# voice is 'vla', 't-vla', 'a-vla', 'violetta' or 'taille'; the violins are 'vl (2)' or
# '2 vl'. Matching only 'vl (2), vla, vlc' drops 71 'vl (2), vla, b' sources and with
# them 18 downloadable digitizations -- including the sole Biblioteca Nacional one.
# Keyboard reductions ('cemb (2)') and flute or piano quartets are deliberately out.
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
KINDS = ('iiif', 'image', 'digitized', 'other')
FETCHABLE = ('iiif', 'image', 'digitized')


def fetch(url, accept='*/*', ua=UA, tries=4):
    """(bytes, final_url). The final URL matters: SBB hides the PPN in its redirect."""
    for i in range(tries):
        try:
            with urlopen(Request(url, headers={'Accept': accept, 'User-Agent': ua}), timeout=90) as r:
                return r.read(), r.geturl()
        except Exception:
            if i == tries - 1: raise
            time.sleep(2 ** i)


def get(url, accept='application/ld+json', ua=UA):
    return fetch(url, accept, ua)[0]


def person(name):
    d = json.loads(get(f'{BASE}/search?' + urlencode({'mode': 'people', 'q': name})))
    return next(i['id'].rsplit('/', 1)[1] for i in d['items'] if name in json.dumps(i, ensure_ascii=False))


def _page_through(start):
    """One pass over a paginated result. (ids, totalItems).

    A read that dies mid-page ends this pass rather than the run: `sources()` compares the
    union against `totalItems` and walks again, so an abandoned page is picked up next time.
    Swallowing the error is only safe because of that check."""
    ids, total, url = [], None, start
    while url:
        try:
            d = json.loads(get(url))
        except Exception as e:
            print(f'  pass interrupted ({type(e).__name__}); re-walking', file=sys.stderr)
            return ids, total
        if 'items' not in d and d.get('message'):
            sys.exit(f'RISM rejected the query: {d["message"]}')
        if total is None: total = d.get('totalItems')
        ids += [i['id'].rsplit('/', 1)[1] for i in d.get('items', [])]
        n = d.get('view', {}).get('next')
        url = n.get('id') if isinstance(n, dict) else n
    return ids, total


def sources(pid, q, fq, passes=4):
    """Every source id for a person, checked against `totalItems`.

    A single pass is not reliable. RISM intermittently serves a page with no `next`, which
    ends the walk early and silently -- three runs of the same query here returned 613, 462
    and 528 ids. Nothing errors, you just quietly harvest less than exists. So compare each
    pass against `totalItems` and union further passes until the count is reached.
    `rism_incipits.py` paginates the same way and has the same exposure."""
    p = {'rows': 100} | ({'q': q} if q else {})
    start = f'{BASE}/people/{pid}/sources?' + urlencode(p) + ''.join(f'&fq={f}' for f in fq if f)
    seen, total = {}, None
    for i in range(passes):
        ids, t = _page_through(start)
        total = t if total is None else total
        seen |= dict.fromkeys(ids)
        if total is None or len(seen) >= total: break
        print(f'  pagination returned {len(seen)}/{total}; re-walking ({i + 1})', file=sys.stderr)
        time.sleep(1)
    if total and len(seen) < total:
        print(f'WARNING: {len(seen)} of {total} sources after {passes} passes', file=sys.stderr)
    return list(seen)


def fields(rec, tag):
    return [{s.get('code'): s.text or '' for s in df.iter(M + 'subfield')}
            for df in rec.iter(M + 'datafield') if df.get('tag') == tag]


def marc(sid, cache):
    """Cached MARCXML. Shares `.rism-cache/` with rism_incipits.py -- delete to re-fetch."""
    f = cache / f'{sid}.xml'
    if not f.exists():
        f.write_bytes(get(f'{BASE}/sources/{sid}', 'application/marcxml+xml'))
        time.sleep(.25)
    return ET.parse(f).getroot()


def is_gerard(c):
    return c.get('0') == GERARD_PUB or bool(GERARD.search(c.get('a', '')))


def gnum(g):
    """Sort key for a Gerard number: '195' < '206/3' < 'deest' < missing."""
    m = re.match(r'\s*(\d+)(.*)', g or '')
    return (int(m[1]), m[2].strip()) if m else (10**9, g or '￿')


def kind(d):
    """Classify one 856 by what you can do with it. See the module docstring."""
    x = d.get('x', '')
    if 'IIIF' in x: return 'iiif'
    if d.get('q', '').startswith('image/'): return 'image'
    if x == 'Digitized': return 'digitized'
    return 'other'


def safe(s, n=60):
    return re.sub(r'_+', '_', re.sub(r'[^\w.-]', '_', (s or '').strip()))[:n].strip('_') or 'unknown'


# Muscat attachments are mostly photographed music pages, but some are watermark shots
# ('..._wm_R ROMANI countermark...'). Same field, different thing -- kept, but filed apart
# so a directory of pages is all music.
WM = re.compile(r'_wm_|watermark|wasserzeichen|countermark', re.I)


def cell(v):
    """A markdown table cell. Shelfmarks really do contain pipes -- E-Mn 'Mp/2393|2' -- and
    one unescaped pipe silently shifts every later column in the row."""
    return str(v).replace('|', '\\|').replace('\n', ' ') if v not in (None, '') else '—'


def is_watermark(r):
    return bool(WM.search((r.get('label') or '') + ' ' + r['url'] + ' ' + (r.get('note') or '')))


# --- metadata -----------------------------------------------------------------
# RISM links per-holding detail to a holdings record with $3 ('holdings/199629').
# 852 defines the holdings; 593 (source type), 300 (extent), 561 (provenance) and
# 592 (watermark) repeat per holding. Fields without $3 describe the whole source.

def describe(sid, rec):
    """The MARC story for one source: bibliographic core plus a dict of holdings."""
    lead = (rec.findtext(M + 'leader') or '')
    ut = (fields(rec, '240') or [{}])[0]
    cat = fields(rec, '690')
    pub = (fields(rec, '260') or [{}])[0]
    hold = {}
    for h in fields(rec, '852'):
        hold[h.get('3') or f'_{len(hold)}'] = dict(
            siglum=h.get('a'), institution=h.get('e'), shelfmark=h.get('c'),
            former_shelfmark=h.get('d'), institution_id=h.get('x'))
    def attach(tag, key, codes):
        for d in fields(rec, tag):
            v = {k: d.get(k) for k in codes if d.get(k)}
            if not v: continue
            t = hold.get(d.get('3'))
            for tgt in ([t] if t else hold.values() or [{}]):
                tgt.setdefault(key, ' · '.join(v.values()))
    attach('593', 'source_type', 'a')         # Print / Manuscript copy / Autograph manuscript
    attach('300', 'extent', 'ac')             # '4 parts', dimensions
    attach('561', 'provenance', 'a')
    attach('592', 'watermark', 'a')
    return dict(
        source=f'{BASE}/sources/{sid}', source_id=sid,
        title=ut.get('a') or (fields(rec, '245') or [{}])[0].get('a'),
        full_title=(fields(rec, '245') or [{}])[0].get('a'),
        key=ut.get('r'), scoring=ut.get('m') or (fields(rec, '594') or [{}])[0].get('a'),
        gerard=next((c.get('n') for c in cat if is_gerard(c)), None),
        # A complete-opus print carries a GerB number for each of its six quartets. Filing it
        # under whichever 690 happens to come first is misleading -- it reads as a scan of
        # that one work -- and the first is not even the lowest: RISM hands back G180-177 and
        # G240-239 in that order. So keep the sorted set and label the span.
        gerard_numbers=sorted({c.get('n') for c in cat if is_gerard(c) and c.get('n')}, key=gnum),
        catalogs=[f"{c.get('a', '')} {c.get('n', '')}".strip() for c in cat],
        # Leader/06 'c' = printed notated music, 'd' = manuscript notated music.
        # 593 $a is the finer reading and the one that names an autograph.
        record_type={'c': 'print', 'd': 'manuscript'}.get(lead[6:7], lead[6:7]),
        source_types=sorted({d['a'] for d in fields(rec, '593') if d.get('a')}),
        is_autograph=any('utograph' in (d.get('a') or '') for d in fields(rec, '593')),
        plate_numbers=[d['a'] for d in fields(rec, '028') if d.get('a')],
        published=dict(place=pub.get('a'), publisher=pub.get('b'), date=pub.get('c')),
        physical=[' | '.join(filter(None, (d.get('d'), d.get('m')))) for d in fields(rec, '340')],
        extent=sorted({d['a'] for d in fields(rec, '300') if d.get('a')}),
        notes=[d['a'] for d in fields(rec, '500') if d.get('a')],
        incipits=len([i for i in fields(rec, '031') if i.get('p')]),
        gerard_label=None, holdings=hold)


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
    """Scoring decides. 240 $m is the uniform-title scoring; 594 $a is RISM's own reading
    of the parts and is present when 240 $m is not. Only a record with neither falls back
    to its title, so a 'Quartets' record for two harpsichords is not mistaken for one."""
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


CORRECTIONS = [None]


def corrections(path=Path('corrections.json')):
    """Hand-established facts that override RISM, keyed by source id.

    RISM is not always wrong so much as incomplete. Pleyel's 'Douze quatuors, oeuvre 39'
    anthology (source 990005884) is twelve Boccherini quartets issued in four livraisons of
    three, and RISM records a single GerB number for the whole publication -- so the only way
    to know a livraison holds G 201 and G 203 alongside it is to look. What is established by
    looking belongs here, not in a patched harvest, and RISM's own values are kept as
    `*_rism` so the two never get confused."""
    if CORRECTIONS[0] is None:
        try:
            CORRECTIONS[0] = {k: v for k, v in json.loads(path.read_text()).items()
                              if not k.startswith('_')}
        except Exception:
            CORRECTIONS[0] = {}
    return CORRECTIONS[0]


def apply_correction(meta, siglum=None, shelfmark=None, holding=None):
    """Overlay a correction onto one source, keeping RISM's reading beside it.

    Corrections are keyed by source id, but a `holdings` block keyed by siglum overrides one
    copy only. That distinction is not academic: RISM catalogues Pleyel's twelve-quartet
    'oeuvre 39' as a single record, and its Rochester copy is livraison 1 while its Berlin
    copy is livraison 3 -- the same record, different music. A source-level correction would
    put Rochester's contents on Berlin's shelf."""
    c = corrections().get(meta['source_id'])
    if not c: return meta
    hh = c.get('holdings') or {}
    # A RISM-linked copy is matched by its holdings id, which is the only stable handle:
    # Berlin's three livraisons share one shelfmark, so nothing else distinguishes them.
    h = next((v for v in hh.values() if holding and v.get('holding') == holding), None) \
        or (hh.get(f'{siglum} {shelfmark}'.strip()) if shelfmark else None) \
        or hh.get(siglum or '')
    if not h and c.get('holdings') and not c.get('contents'):
        # The source is known to differ per copy, but this one has no entry yet.
        meta = dict(meta)
        meta['correction_note'] = c.get('note')
        meta['corrected'] = True
        return meta
    meta = dict(meta)
    spec = {**{k: v for k, v in c.items() if k != 'holdings'}, **(h or {})}
    meta['corrected'] = True
    meta['correction_note'] = ' — '.join(filter(None, (c.get('note'), (h or {}).get('note'))))
    meta['established_by'] = spec.get('established_by')
    meta['livraison'] = spec.get('livraison')
    if spec.get('contents'):
        meta['contents'] = spec['contents']
        found = sorted({w['gerard'] for w in spec['contents'] if w.get('gerard')}, key=gnum)
        meta['unidentified_works'] = sum(1 for w in spec['contents'] if not w.get('gerard'))
        if found:
            meta['gerard_numbers_rism'] = meta['gerard_numbers']
            meta['gerard_numbers'] = found
    for k in ('shelfmark', 'title'):
        if k in spec: meta[k] = spec[k]
    return meta


def gerard_label(nums):
    """'201' for one, '201-206' for a run, '159, 162, 164' for a handful."""
    if not nums: return None
    if len(nums) == 1: return nums[0]
    lo, hi = nums[0], nums[-1]
    if all(n.isdigit() for n in nums) and int(hi) - int(lo) == len(nums) - 1:
        return f'{lo}-{hi}'
    return ', '.join(nums)


def rows(sid, cache, everything, pid):
    try:
        rec = marc(sid, cache)
    except Exception as e:
        print(f'skip {sid}: {e}', file=sys.stderr)
        return []
    if not by_composer(rec, pid): return []        # Boccherini as dedicatee, not composer
    if not (everything or is_quartet(rec)): return []
    base = describe(sid, rec)
    out = []
    hs = base['holdings']
    for d in fields(rec, '856'):
        if not d.get('u'): continue
        # A single-holding record links nothing -- neither its 852 nor its 856 carries $3 --
        # so an unlinked 856 on a one-holding source belongs to that holding.
        h = hs.get(d.get('3')) or (next(iter(hs.values())) if len(hs) == 1 else {})
        meta = apply_correction(base, h.get('siglum'), h.get('shelfmark'), d.get('3'))
        meta['gerard_label'] = gerard_label(meta['gerard_numbers'])
        out.append(dict(kind=kind(d), url=d['u'], note=d.get('z'), label=d.get('y'),
                        mime=d.get('q'), holding=d.get('3'),
                        siglum=h.get('siglum'), institution=h.get('institution'),
                        shelfmark=h.get('shelfmark'),
                        former_shelfmark=h.get('former_shelfmark'),
                        source_type=h.get('source_type'),
                        holding_extent=h.get('extent'),
                        # When several holdings share one record and the link names none,
                        # keep every siglum rather than silently picking one.
                        all_sigla=sorted({v['siglum'] for v in hs.values() if v.get('siglum')}),
                        meta=meta))
    return out


# --- resolvers: a landing page -> something downloadable ----------------------
# Each returns ('iiif', manifest_url) or ('files', [urls]) or None.

def r_sbb(u):
    """Staatsbibliothek Berlin: the PPN only appears in the resolver's redirect."""
    ppn = re.search(r'PPN=(\w+)', fetch(u, ua=BROWSER)[1])
    return ('iiif', f'https://content.staatsbibliothek-berlin.de/dc/{ppn[1]}/manifest') if ppn else None


def r_mdz(u):
    m = re.search(r'(bsb\d+)', u)
    return ('iiif', f'https://api.digitale-sammlungen.de/iiif/presentation/v2/{m[1]}/manifest') if m else None


def r_gallica(u):
    m = re.search(r'ark:/(\d+)/([\w.]+)', u)
    return ('iiif', f'https://gallica.bnf.fr/iiif/ark:/{m[1]}/{m[2]}/manifest.json') if m else None


def r_handle(u):
    """Handle -> target. For Rochester's urresearch, scrape the per-part PDF links."""
    m = re.search(r'handle\.net/([\d.]+/\w+)', u)
    # The handle API rate-limits a run like this one and answers 500 for a while; it is
    # the same id that resolves fine a minute later, so be patient rather than give up
    # and file the item as unreachable.
    d = json.loads(fetch(f'https://hdl.handle.net/api/handles/{m[1]}',
                         'application/json', UA, tries=6)[0])
    tgt = next((v['data']['value'] for v in d.get('values', [])
                if v.get('type') == 'URL'), None)
    if not tgt or 'urresearch.rochester.edu' not in tgt: return None
    html = get(tgt, 'text/html', BROWSER).decode('utf8', 'replace')
    ids = dict.fromkeys(re.findall(
        r'href="(/fileDownloadForInstitutionalItem\.action\?itemId=\d+&(?:amp;)?itemFileId=\d+)"', html))
    return ('files', [f'https://urresearch.rochester.edu{i.replace("&amp;", "&")}' for i in ids]) or None


RESOLVERS = ((re.compile(r'resolver\.staatsbibliothek-berlin\.de'), r_sbb),
             (re.compile(r'mdz-nbn-resolving\.de|digitale-sammlungen'), r_mdz),
             (re.compile(r'gallica\.bnf\.fr'), r_gallica),
             (re.compile(r'hdl\.handle\.net'), r_handle))


def resolve(r, cache=None):
    """One inventory row -> ('iiif'|'files', payload). Unresolvable landing pages -> None.

    Successful resolutions are cached in `.rism-cache/resolved.json`, because resolving is
    the fragile half: Rochester's handle API rate-limits a run of this size and starts
    answering 500 to ids that resolve perfectly a minute later. Once an id is known, a
    re-run never asks again. Failures are deliberately not cached."""
    # A link known to lead somewhere wrong is worse than one that simply fails.
    if any(p.search(r['url']) for p, _ in BLOCKED): return None
    if r['kind'] == 'iiif': return ('iiif', r['url'])
    if r['kind'] == 'image': return ('files', [r['url']])
    if cache is not None and r['url'] in cache:
        k, v = cache[r['url']]
        return (k, v)
    for pat, fn in RESOLVERS:
        if pat.search(r['url']):
            try:
                got = fn(r['url'])
                if got and cache is not None:
                    cache[r['url']] = list(got)
                    save_resolved(cache)
                return got
            except Exception as e:
                print(f"  ! resolve {r['url']}: {e}", file=sys.stderr)
            return None
    return None


RESOLVED_PATH = [None]


def load_resolved(cachedir):
    RESOLVED_PATH[0] = cachedir / 'resolved.json'
    try:
        return json.loads(RESOLVED_PATH[0].read_text())
    except Exception:
        return {}


def save_resolved(d):
    try:
        RESOLVED_PATH[0].write_text(json.dumps(d, ensure_ascii=False, indent=1))
    except Exception:
        pass


# --- IIIF --------------------------------------------------------------------

def label(v):
    if isinstance(v, dict): return next(iter(v.values()))[0] if v else None
    return v[0] if isinstance(v, list) else v


REFRESH = re.compile(rb'http-equiv="refresh"[^>]*?url=([^"\'>]+)', re.I)


def manifest_bytes(url, hops=3):
    """A manifest, or ValueError. Harvard serves a 200 HTML 'this has moved' page with a
    meta refresh instead of a redirect, so follow that before deciding it isn't JSON."""
    for _ in range(hops):
        data = get(url, 'application/json', BROWSER)
        s = data.lstrip()[:1]
        if s in (b'{', b'['):
            json.loads(data)                         # parse now, so we never cache garbage
            return data
        m = REFRESH.search(data)
        if not m: break
        url = m[1].decode().strip()
    raise ValueError(f'not a IIIF manifest: {url}')


def canvases(data):
    """[(label, image-API base or None, direct url, w, h)] from a v2 or v3 manifest."""
    d = json.loads(data)
    out = []
    if d.get('sequences'):                                    # Presentation v2
        for c in d['sequences'][0].get('canvases', []):
            im = (c.get('images') or [{}])[0].get('resource', {})
            svc = im.get('service') or {}
            if isinstance(svc, list): svc = svc[0] if svc else {}
            out.append((label(c.get('label')), svc.get('@id') or svc.get('id'),
                        im.get('@id'), c.get('width'), c.get('height')))
    else:                                                     # Presentation v3
        for c in d.get('items', []):
            body = ((c.get('items') or [{}])[0].get('items') or [{}])[0].get('body', {})
            svc = body.get('service') or {}
            if isinstance(svc, list): svc = svc[0] if svc else {}
            out.append((label(c.get('label')), svc.get('@id') or svc.get('id'),
                        body.get('id'), c.get('width'), c.get('height')))
    return out


def caps(svc):
    """(maxWidth, maxHeight, width, height) from info.json -- the per-request ceiling."""
    try:
        d = json.loads(get(f'{svc}/info.json', 'application/json', BROWSER))
    except Exception:
        return None, None, None, None
    mw = d.get('maxWidth')
    return mw, d.get('maxHeight') or mw, d.get('width'), d.get('height')


def fetch_page(svc, direct, out, full):
    """One page to `out`. Tiled and stitched only where the server caps below full size."""
    if not svc:
        out.write_bytes(get(direct, 'image/jpeg', BROWSER))
        return f'{out.name} direct'
    mw, mh, w, h = caps(svc)
    if not (full and w and h and mw and (w > mw or h > mh)):
        out.write_bytes(get(f'{svc}/full/max/0/default.jpg', 'image/jpeg', BROWSER))
        return f'{out.name} {"<=%dpx" % mw if mw else "full"}'
    from PIL import Image
    im = Image.new('RGB', (w, h))
    n = 0
    for y in range(0, h, mh):
        for x in range(0, w, mw):
            rw, rh = min(mw, w - x), min(mh, h - y)
            t = get(f'{svc}/{x},{y},{rw},{rh}/max/0/default.jpg', 'image/jpeg', BROWSER)
            im.paste(Image.open(io.BytesIO(t)).resize((rw, rh)), (x, y))
            n += 1
    im.save(out, quality=92)
    return f'{out.name} {w}x{h} ({n} tiles)'


def named_file(url, i, tries=4):
    """(name, bytes). Rochester names each part in Content-Disposition ('...viola.pdf'),
    which is the only place the part name appears -- so read it from the headers."""
    for t in range(tries):
        try:
            with urlopen(Request(url, headers={'User-Agent': BROWSER}), timeout=120) as r:
                cd = r.headers.get('Content-Disposition') or ''
                m = re.search(r'filename="?([^";]+)', cd)
                return (safe(m[1]) if m else safe(url.rsplit('/', 1)[-1]) or f'{i:03d}.bin'), r.read()
        except Exception as e:
            if t == tries - 1: return None, str(e)
            time.sleep(2 ** t)


# --- output ------------------------------------------------------------------

def readme(r, got):
    m = r['meta']
    p = m['published']
    L = [f"# {m['title'] or '(untitled)'}",
         '', f"RISM source [{m['source_id']}]({m['source']})"
             + (f" · Gérard **G {m.get('gerard_label') or m['gerard']}**"
                if m['gerard'] else ' · **no Gérard number in RISM**'),
         '']
    def row(k, v):
        if v: L.append(f'- **{k}:** {v}')
    row('Held at', ' · '.join(filter(None, (r['siglum'], r['institution']))))
    row('Shelfmark', r['shelfmark'])
    row('Former shelfmark', r['former_shelfmark'])
    if not r['siglum'] and r['all_sigla']:
        row('Holdings on this record', ' · '.join(r['all_sigla'])
            + ' — the link names no single holding')
    row('Source type', r['source_type'] or ', '.join(m['source_types']) or m['record_type'])
    row('Autograph', 'yes' if m['is_autograph'] else None)
    row('Scoring', m['scoring'])
    row('Key', m['key'])
    row('Parts / extent', r['holding_extent'] or ', '.join(m['extent']))
    row('Plate number', ', '.join(m['plate_numbers']))
    row('Published', ' · '.join(filter(None, (p['place'], p['publisher'], p['date']))))
    row('Physical', ', '.join(m['physical']))
    row('Catalogues', ' · '.join(m['catalogs']))
    if m.get('corrected'):
        row('Livraison', m.get('livraison'))
        row('Corrected by hand', m.get('correction_note'))
        row('Established by', m.get('established_by'))
        if m.get('gerard_numbers_rism'):
            row('RISM records only', 'G ' + ', '.join(m['gerard_numbers_rism']))
        if m.get('contents'):
            row('Contents', ' · '.join(
                f"{w['n']}. G {w['gerard']}" if w.get('gerard') else f"{w['n']}. unidentified"
                for w in m['contents']))
    row('Incipits in RISM', m['incipits'] or '0 — a transcription target')
    row('Digitization', f"{r['kind']} · <{r['url']}>")
    row("Library's own title for the scan", r.get('manifest_label'))
    if r.get('label_unverified'):
        row('Check', "the scan's own title does not name Boccherini — confirm it is "
                     'the right book before trusting these images')
    row('Files here', got)
    if m['notes']:
        L += ['', '## Notes', ''] + [f'- {n}' for n in m['notes']]
    return '\n'.join(L) + '\n'


# Why a link cannot be fetched from a script. Each was established by trying it.
BLOCKED = (
    (re.compile(r'nbn-resolving\.(org|de)'),
     'Anubis proof-of-work bot gate. The page returns a JavaScript challenge instead of '
     'the record, and `nbn-resolving.de` redirects to the same `.org` host. A browser '
     'solves it silently, so the link below works when you click it.'),
    (re.compile(r'bne\.es'),
     'The server accepts the TCP connection then never completes the TLS handshake for us, '
     'so no request is ever sent. Likely an egress-IP block; try it from your own machine.'),
    (re.compile(r'manuscriptorium\.com'),
     'Needs a portal session before it will serve images; the record URL alone returns no manifest.'),
    (re.compile(r'iiif\.lib\.harvard\.edu/manifests/drs:'),
     "RISM's link is broken at Harvard's end. The DRS id 404s on Harvard's image server, and "
     'the only thing the redirect chain yields is a manifest for a completely different work '
     "(Campra, *L'Europe galante*, 284 pages). Downloading it would file someone else's ballet "
     'under this Gérard number, so it is refused. Search Harvard by the shelfmark below instead.'),
)


NO_PAGES = ('The library serves a valid IIIF manifest for this record whose `canvases` list is '
            'empty -- it has the structure and the title but no page images published. '
            'Nothing to download until they publish them; the viewer link is worth a look in '
            'case it appears there first.')


def why_blocked(r):
    if r.get('no_pages'): return NO_PAGES
    return next((m for p, m in BLOCKED if p.search(r['url'])),
                'No resolver written for this host yet.')


def manual_list(recs, outdir):
    """MANUAL-DOWNLOADS.md -- every music link a script cannot reach, with a deep link."""
    # A source often carries two links to the same scan -- a IIIF manifest and the landing
    # page in front of it. If either one delivered files, the other is not work to do.
    have = {(r['meta']['source_id'], r['holding'] or r['siglum'])
            for r in recs if r.get('files')}
    todo = [r for r in recs if r['kind'] in FETCHABLE
            and (r.get('unresolved') or r.get('no_pages'))
            and (r['meta']['source_id'], r['holding'] or r['siglum']) not in have]
    seen, groups = set(), {}
    for r in todo:
        if r['url'] in seen: continue
        seen.add(r['url'])
        groups.setdefault(why_blocked(r), []).append(r)
    L = ['# Manual downloads',
         '', 'Music that RISM links but this script cannot fetch. Every URL here is a deep',
         'link straight to the item -- opening it in a browser should land on the viewer.',
         '', f'{len(seen)} items. Everything else in the inventory downloaded automatically.',
         '']
    if not seen:
        L.append('Nothing outstanding.')
    for reason, rs in groups.items():
        L += [f'## {len(rs)} item(s)', '', f'*Why not scripted:* {reason}', '']
        for r in sorted(rs, key=lambda r: (gnum(r['meta']['gerard']), r['meta']['source_id'])):
            m = r['meta']
            p = m['published']
            L.append(f"### {('G ' + m['gerard']) if m['gerard'] else 'G unknown'} — "
                     f"{' '.join(filter(None, (r['siglum'], r['shelfmark']))) or m['source_id']}")
            L.append('')
            L.append(f"**[Open the scan]({r['url']})**")
            L.append('')
            for k, v in (('Title', m['title']), ('Full title', (m['full_title'] or '')[:170]),
                         ('Held at', ' · '.join(filter(None, (r['siglum'], r['institution'])))),
                         ('Shelfmark', r['shelfmark']), ('Former shelfmark', r['former_shelfmark']),
                         ('Type', (r['source_type'] or ', '.join(m['source_types']))
                          + (' — AUTOGRAPH' if m['is_autograph'] else '')),
                         ('Parts', r['holding_extent'] or ', '.join(m['extent'])),
                         ('Plate number', ', '.join(m['plate_numbers'])),
                         ('Published', ' · '.join(filter(None, (p['place'], p['publisher'], p['date'])))),
                         ('Scoring', m['scoring']),
                         ('RISM record', f"<{m['source']}>"),
                         ('Save as', f"`digitizations/{dirname(r)}/{manual_filename(r)}`"
                                     ' — the folder already exists, with its `metadata.json`'
                                     ' and `README.md` waiting for the file')):
                if v and v.strip(' —,'): L.append(f'- **{k}:** {v}')
            L.append('')
            stub(r, outdir)
    (outdir / 'MANUAL-DOWNLOADS.md').write_text('\n'.join(L))
    return len(seen)


def fetch_declared(d, spec, full=False, limit=0):
    """Download a hand-registered copy that declares an `iiif` manifest.

    A correction can name a scan RISM links to nothing -- Munich's four Pleyel livraisons,
    found in a saved MDZ search page. Where the library's IIIF server answers, there is no
    reason to make anyone click through it page by page."""
    man = spec.get('iiif')
    if not man: return 0
    mf = d / 'manifest.json'
    try:
        if not mf.exists(): mf.write_bytes(manifest_bytes(man))
        cs = canvases(mf.read_bytes())
    except Exception as e:
        mf.unlink(missing_ok=True)
        print(f'  ! {man}: {e}', file=sys.stderr)
        return 0
    if not cs: return 0
    # The page images may have been collated into a PDF and moved to Trash. That PDF holds
    # the same JPEG bytes (see verify_pdfs.py), so the item is complete and must not be
    # fetched again -- otherwise freeing the disk space silently re-downloads 8 GB, over
    # links that in several cases no longer resolve.
    if pdf_is_complete(d, len(cs)):
        print(f'{d}: {len(cs)} pages already in {d.name}.pdf', file=sys.stderr)
        return 0
    print(f'{d}: {len(cs)} pages', file=sys.stderr)
    n = 0
    for i, (lab, svc, direct, w, h_) in enumerate(cs, 1):
        if limit and i > limit: break
        f = d / f'{i:03d}.jpg'
        if f.exists() and f.stat().st_size: continue
        try:
            print('  ' + fetch_page(svc, direct, f, full), file=sys.stderr)
            n += 1
        except Exception as e:
            print(f'  ! page {i}: {e}', file=sys.stderr)
        time.sleep(.15)
    return n


def hand_found(base_meta, outdir, hs, full=False, limit=0, fetch=False):
    """Folders for copies RISM links no scan for, declared in corrections.json.

    RISM links a digitization for about 5% of what it catalogues, so a copy found directly
    at a library has nowhere to live otherwise -- Berlin's `Mus. 8824` is one, reached from
    the SBB viewer and not from any RISM link."""
    made = []
    c = corrections().get(base_meta['source_id']) or {}
    for key, spec in (c.get('holdings') or {}).items():
        if not spec.get('found_by_hand'): continue
        sig, _, rest = key.partition(' ')
        meta = apply_correction(base_meta, sig, rest or None)
        meta['gerard_label'] = gerard_label(meta['gerard_numbers'])
        r = dict(kind='digitized', url=spec.get('url') or '', note=None, label=None, mime=None,
                 holding=None, siglum=sig, shelfmark=spec.get('shelfmark'), former_shelfmark=None,
                 institution=next((v.get('institution') for v in hs.values()
                                   if v.get('siglum') == sig), None),
                 source_type=None, holding_extent=None, all_sigla=[], meta=meta,
                 found_by_hand=True)
        d = relocate(outdir, dirname(r))
        d.mkdir(parents=True, exist_ok=True)
        want = manual_filename(r)
        have = sorted(f.name for f in d.iterdir()
                      if f.is_file() and f.suffix.lower() in ('.pdf', '.jpg', '.jpeg', '.png'))
        write_sidecar(d, {k: v for k, v in r.items() if k != 'meta'} | meta
                      | {'found_by_hand': True, 'suggested_filename': want})
        (d / 'README.md').write_text(readme(r, ', '.join(have) if have
                                            else f'none yet — save it here as `{want}`')
            + f"""
## Found by hand, not linked by RISM

{spec.get('note') or ''}

**[Open the scan]({spec.get('url') or ''})**"""
            + (f"\n\nIIIF manifest: <{spec['iiif']}>" if spec.get('iiif') else '')
            + f"\n\nSave it here as `{want}`, or as `001.jpg`, `002.jpg` … for a run of pages.\n")
        if fetch and not have: fetch_declared(d, spec, full, limit)
        made.append(d)
    return made


def stub(r, outdir):
    """Create a manual item's folder and its sidecars up front, so a hand-downloaded file
    only has to be dropped in. Without this the folder has to be made by hand, and a folder
    typed into the macOS Finder turns a '/' into ':' -- which is how one of these ended up
    as `G159/G159:450200974_D-Eu`."""
    d = outdir / dirname(r)
    d.mkdir(parents=True, exist_ok=True)
    want = manual_filename(r)
    mf = d / 'metadata.json'
    if not mf.exists():
        mf.write_text(json.dumps(
            {k: v for k, v in r.items() if k != 'meta'} | r['meta']
            | {'downloaded_by_hand': True, 'suggested_filename': want,
               'why_manual': why_blocked(r)}, ensure_ascii=False, indent=1))
    # Rewritten every run, so the 'Files here' line stops saying 'none yet' once the file
    # has actually been saved.
    have = sorted(f.name for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() in ('.pdf', '.jpg', '.jpeg', '.png', '.tif'))
    rf = d / 'README.md'
    if True:
        rf.write_text(readme(r, (', '.join(have) if have
                                 else f'none yet — save the download here as `{want}`'))
                      + f"""
## This one is a hand download

{why_blocked(r)}

{'**Done** — the file below is in place.' if have else ''}
**[Open the scan]({r['url']})**, then save it in this folder. Name it `{want}` if it is a
single PDF; if the library gives you a run of page images instead, name them `001.jpg`,
`002.jpg` … in page order, which is what the IIIF downloads here use. Either way
`build_sources_page.py` will pick the item up on its next run — it keys off this
`metadata.json`, so leave that in place.
""")


def manual_filename(r, ext='pdf'):
    """What to call a hand-downloaded file. Libraries name their exports opaquely --
    Eichstaett serves `pid_14976997.pdf` -- so name it by siglum and shelfmark, which is
    how every other item here is identified, and keep the original name in metadata.json."""
    return safe(f"{r['siglum'] or 'unknown'}_{r['shelfmark'] or r['meta']['source_id']}", 70) + '.' + ext


def gdir(g):
    """'201' -> G201, 'No. 207-212' -> G207-212, '275/3' -> G275-3, None -> unidentified."""
    if not g: return 'unidentified'
    return 'G' + safe(re.sub(r'^\s*(No\.?|Nr\.?)\s*', '', g).replace('/', '-'), 14)


def item_name(r):
    """`<source>_<siglum>`, plus the shelfmark when one library holds two copies.

    Berlin holds Pleyel's 'oeuvre 39' twice under RISM source 990005884 -- `DMS 51778` and
    `Mus. 8824` -- and they are different livraisons, so the siglum alone cannot name the
    folder."""
    base = f"{r['meta']['source_id']}_{r['siglum'] or r['kind']}"
    # Berlin holds three livraisons of Pleyel's 'oeuvre 39', all under the one shelfmark
    # DMS 51778, so the shelfmark cannot tell them apart -- the instalment can.
    if r['meta'].get('livraison'):
        base += f"_livr{r['meta']['livraison']}"
    else:
        sigla = [h.get('siglum') for h in r['meta']['holdings'].values()]
        if r['siglum'] and sigla.count(r['siglum']) > 1 and r.get('shelfmark'):
            base += '_' + r['shelfmark']
    return safe(base, 64)


def dirname(r):
    d = Path(gdir(r['meta'].get('gerard_label') or r['meta']['gerard'])) / item_name(r)
    return d / 'watermarks' if is_watermark(r) else d


def relocate(outdir, want):
    """Move an item's folder when its Gerard span changes, instead of re-fetching it.

    A folder is named after the works it contains, so a correction can rename it -- and the
    downloader would otherwise see an empty target and pull everything again. The item id
    (`<source>_<siglum>`) is stable, so an existing folder with that name elsewhere in the
    tree is the same item and gets moved."""
    d = outdir / want
    if d.exists(): return d
    stem = '_'.join(want.name.split('_')[:2])          # <source>_<siglum>
    # The fallback exists so adding a shelfmark to a folder name does not re-download it.
    # It must only match a name the new one *extends*: `..._D-B` -> `..._D-B_DMS_51778` is
    # the same item, `..._D-B_DMS_51778` -> `..._D-B_Mus._8824` is a different copy, and
    # matching on the shared `..._D-B` prefix moved one library's livraison into another's.
    cands = [o for o in outdir.glob(f'*/{want.name}')]
    if not cands:
        cands = [o for o in outdir.glob(f'*/{stem}*')
                 if o.is_dir() and want.name.startswith(o.name)]
        if len(cands) != 1: cands = []
    for old in cands:
        if old.is_dir() and old != d:
            d.parent.mkdir(parents=True, exist_ok=True)
            for f in old.iterdir():
                tgt = d / f.name
                if not tgt.exists(): f.rename(tgt) if d.exists() else None
            if not d.exists():
                old.rename(d)
            else:
                for f in list(old.iterdir()):
                    if not (d / f.name).exists(): f.rename(d / f.name)
                    else: f.unlink()
                old.rmdir()
            print(f'  ~ moved {old.relative_to(outdir)} -> {want}', file=sys.stderr)
            return d
    return d


cache_dir = [Path('.rism-cache')]


def download(recs, outdir, full, limit, rcache=None):
    """Fetch every fetchable link. Existing files are left alone, so re-runs resume."""
    seen, pages = set(), 0
    for r in recs:
        if r['kind'] not in FETCHABLE or r['url'] in seen: continue
        seen.add(r['url'])
        res = resolve(r, rcache)
        d = relocate(outdir, dirname(r))
        if not res:
            r['unresolved'] = True
            print(f"  - no resolver: {r['url']}", file=sys.stderr)
            continue
        d.mkdir(parents=True, exist_ok=True)
        write_sidecar(d, {k: v for k, v in r.items() if k != 'meta'} | r['meta'])
        got = []
        if res[0] == 'files':
            # Third page-writing path, after the two manifest loops: Muscat attachments and
            # Rochester's part files, named from Content-Disposition. It too must respect a
            # collated PDF, or freeing disk space quietly refetches these.
            if pdf_is_complete(d, len(res[1])):
                r['files'] = [f'{d.name}.pdf']
                r['collated_only'] = True
                print(f'{d}: {len(res[1])} file(s) already in {d.name}.pdf', file=sys.stderr)
                (d / 'README.md').write_text(readme(r, f'{len(res[1])} — collated into {d.name}.pdf'))
                continue
            for i, u in enumerate(res[1], 1):
                nm, data = named_file(u, i)
                if not nm:
                    print(f'  ! {u}: {data}', file=sys.stderr)
                    r.setdefault('failed', []).append(u)
                    continue
                f = d / nm
                if not f.exists():
                    f.write_bytes(data)
                    print(f'  {d.name}/{nm} ({len(data)//1024}k)', file=sys.stderr)
                    pages += 1
                    time.sleep(.2)
                got.append(nm)
        else:
            mf = d / 'manifest.json'
            try:
                if not mf.exists(): mf.write_bytes(manifest_bytes(res[1]))
                cs = canvases(mf.read_bytes())
            except Exception as e:
                mf.unlink(missing_ok=True)
                r['unresolved'] = True
                print(f'  ! manifest {res[1]}: {e}', file=sys.stderr)
                continue
            # What the holding library calls this book, which is not always what RISM says
            # it is -- a mismatch here is how a mislinked record shows itself.
            r['manifest_label'] = label(json.loads(mf.read_bytes()).get('label'))
            ml = (r['manifest_label'] or '').lower()
            if ml and 'boccherini' not in ml and 'bocherini' not in ml:
                r['label_unverified'] = True
            if not cs:
                # A real manifest with an empty canvases list: catalogued, not yet scanned.
                r['no_pages'] = True
                print(f'  - no page images published: {res[1]}', file=sys.stderr)
                continue
            # Same guard as the hand-found path: if the collated PDF already holds these
            # pages, the images were moved to Trash on purpose and must not be refetched.
            if pdf_is_complete(d, len(cs)):
                r['files'] = [f'{i:03d}.jpg' for i in range(1, len(cs) + 1)]
                r['collated_only'] = True
                print(f'{d}: {len(cs)} pages already in {d.name}.pdf', file=sys.stderr)
                (d / 'README.md').write_text(readme(r, f'{len(cs)} — collated into {d.name}.pdf'))
                continue
            print(f'{d}: {len(cs)} pages — {(r["meta"]["title"] or "")[:50]}', file=sys.stderr)
            for i, (lab, svc, direct, w, h) in enumerate(cs, 1):
                if limit and i > limit: break
                f = d / f'{i:03d}.jpg'
                got.append(f.name)
                if f.exists() and f.stat().st_size: continue
                try:
                    print('  ' + fetch_page(svc, direct, f, full), file=sys.stderr)
                    pages += 1
                except Exception as e:
                    print(f'  ! page {i}: {e}', file=sys.stderr)
                time.sleep(.15)
        r['files'] = got
        (d / 'README.md').write_text(readme(r, f'{len(got)} — see this directory'))
    seen_src = {r['meta']['source_id'] for r in recs}
    for sid in seen_src:
        m = next(r['meta'] for r in recs if r['meta']['source_id'] == sid)
        hand_found(m, outdir, m['holdings'], full, limit, fetch=True)
    # A correction can name a source that carries no 856 at all -- S-Skma's W 4-R is
    # catalogued by RISM but linked to nothing -- so those never reach the loop above.
    for sid in corrections():
        if sid in seen_src: continue
        try:
            meta = describe(sid, marc(sid, cache_dir[0]))
        except Exception as e:
            print(f'  ! correction {sid}: {e}', file=sys.stderr)
            continue
        hand_found(meta, outdir, meta['holdings'], full, limit, fetch=True)
    return pages


MEDIA = {'.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'}


def norm_shelf(s):
    """Shelfmarks get written loosely -- 'Mus.ms. 573' vs 'Mus. ms 573' vs 'Mus ms.573'.
    Compare on letters and digits alone.

    Returns '' for anything with no digit in it, which makes it unusable as a key. RISM
    writes 679 holdings as '[no indication]', and matching on that would join every
    shelfmark-less holding at a library to whichever one of them we happen to hold. It is
    the only digit-free shelfmark in the data, so nothing real is lost."""
    n = re.sub(r'[^a-z0-9]', '', (s or '').lower())
    return n if any(c.isdigit() for c in n) else ''


def on_disk(outdir):
    """What we already hold, keyed the two ways an unlinked holding can be recognised:
    by RISM holdings id, and by siglum + shelfmark for copies that arrived off a library
    portal with no RISM link. A folder counts only if it actually contains media -- the
    manual-download stubs carry sidecars and no scan."""
    hid, shelf = {}, {}
    out = Path(outdir)
    for p in sorted(out.rglob('metadata.json')):
        d = p.parent
        if not any(f.suffix.lower() in MEDIA for f in d.iterdir() if f.is_file()):
            continue
        try:
            m = json.loads(p.read_text())
        except Exception:
            continue
        rel = str(d.relative_to(out))
        for k in ('holding', 'rism_holding'):
            if m.get(k):
                hid.setdefault(str(m[k]).rstrip('/').rsplit('/', 1)[-1], set()).add(rel)
        # One shelfmark can hold several sets -- E-Mn M/680-683 is four Bremner part-books
        # bound with both libro secondo and libro terzo -- so a key names a set of folders.
        if m.get('siglum') and norm_shelf(m.get('shelfmark')):
            shelf.setdefault((m['siglum'], norm_shelf(m['shelfmark'])), set()).add(rel)
    return hid, shelf


def write_sidecar(d, payload):
    """Write metadata.json without discarding what this script did not put there.

    The harvester rebuilds a sidecar from RISM on every run. It used to overwrite the file,
    which silently deleted every field added afterwards -- the publisher parsed from a title
    imprint, the normalised `rism_related`, the `page_index` recording what the filenames
    encoded before the images were moved to Trash, and any fact established by looking at a
    scan. They would reappear only if someone happened to re-run the enrichment scripts, and
    vanish again on the next harvest.

    Keys this run produces win, because RISM is authoritative for them. Everything else is
    carried over."""
    f = d / 'metadata.json'
    keep = {}
    if f.exists():
        try:
            keep = {k: v for k, v in json.loads(f.read_text()).items() if k not in payload}
        except Exception:
            keep = {}
    f.write_text(json.dumps(payload | keep, ensure_ascii=False, indent=1))


def pdf_is_complete(d, n_pages):
    """True when `<folder>.pdf` already contains at least the pages we would fetch."""
    f = d / f'{d.name}.pdf'
    if not f.exists() or n_pages <= 0:
        return False
    try:
        out = subprocess.run(['pdfinfo', str(f)], capture_output=True, text=True,
                             timeout=60).stdout
        have = int(next(l.split(':')[1] for l in out.splitlines() if l.startswith('Pages')))
    except Exception:
        return False
    return have >= n_pages


def unlinked_rows(sid, cache, everything, pid):
    """Quartet holdings with no digitization link -- where a scan may exist but RISM
    does not point at it. Cheap: the MARC is already cached by the harvest above."""
    try:
        rec = marc(sid, cache)
    except Exception:
        return []
    if not by_composer(rec, pid): return []
    if not (everything or is_quartet(rec)): return []
    meta = describe(sid, rec)
    hs = meta['holdings']
    dig = {d.get('3') for d in fields(rec, '856') if kind(d) in FETCHABLE}
    out = []
    for hid, h in hs.items():
        if hid in dig: continue
        # A one-holding record links nothing, so any fetchable 856 belongs to that holding.
        if len(hs) == 1 and dig: continue
        if not h.get('siglum'): continue
        out.append(dict(holding=hid, siglum=h['siglum'], institution=h.get('institution'),
                        institution_id=h.get('institution_id'), shelfmark=h.get('shelfmark'),
                        former_shelfmark=h.get('former_shelfmark'),
                        source_type=h.get('source_type') or ', '.join(meta['source_types']),
                        extent=h.get('extent'), source_id=sid, source=meta['source'],
                        title=meta['title'], gerard=meta['gerard'],
                        is_autograph=meta['is_autograph'],
                        plate=', '.join(meta['plate_numbers']),
                        date=meta['published']['date'], incipits=meta['incipits']))
    return out


def unlinked_file(rows_, outdir):
    """UNLINKED-HOLDINGS.md -- the second-pass worklist, by institution, largest first.

    Deliberately not a set of guessed portal URLs. Library search endpoints turned out to be
    inconsistent and several refuse automated requests, so a generated search link would be
    unreliable. Each institution instead gets its RISM page, which lists that library's
    holdings and its own catalogue link, and every source gets its RISM record."""
    hid, shelf = on_disk(outdir)
    for r in rows_:
        g = (hid.get(r['holding'])
             or shelf.get((r['siglum'], norm_shelf(r['shelfmark']))) or set())
        r['got'] = tuple(sorted(g))
        r['got_s'] = ', '.join(f'`{f}`' for f in r['got']) or '—'
    by = {}
    for r in rows_: by.setdefault(r['siglum'], []).append(r)
    tot = len(rows_)
    have = sum(bool(r['got']) for r in rows_)
    L = ['# Quartet holdings with no digitization in RISM',
         '', f'{tot} holdings across {len(by)} libraries. RISM links a scan for only a small',
         'fraction of what it catalogues, so anything here may still be digitized on the',
         "holding library's own portal -- it just is not linked from RISM.",
         '', 'Ordered by how much each library holds, so the top of this list is where a',
         'second pass pays off. **AUTOGRAPH** and *Manuscript copy* rows are the ones no',
         'print edition can replace.',
         '']
    if have:
        L += [f'**{have} of these we now hold anyway** -- found on a library portal and filed by',
              'hand, so RISM still shows no link but the scan is on disk. Those rows carry the',
              'folder in the `got` column; the rest are still open.', '']
    aut = [r for r in rows_ if r['is_autograph']]
    if aut:
        n_open = sum(not r['got'] for r in aut)
        L += [f'## {len(aut)} autograph holdings — check these first'
              + (f' ({n_open} still open)' if n_open != len(aut) else ''), '',
              '| siglum | library | shelfmark | G | source | got |',
              '|---|---|---|---|---|---|']
        for r in sorted(aut, key=lambda r: (bool(r['got']), gnum(r['gerard']))):
            L.append(f"| {cell(r['siglum'])} | {cell((r['institution'] or '')[:40])} "
                     f"| {cell(r['shelfmark'])} | {cell(r['gerard'])} "
                     f"| [{r['source_id']}]({r['source']}) "
                     f"| {r['got_s']} |")
        L.append('')
        # Several autograph records sharing one shelfmark all match the one folder we hold.
        # Mechanically right, but it does not establish which record is which scan.
        dup = {f: n for f, n in
               Counter(f for r in aut for f in r['got']).items() if n > 1}
        for f, n in sorted(dup.items()):
            L += [f'> **`{f}` is matched by {n} of those rows.** They share a shelfmark in RISM,',
                  '> so the match says that folder covers that shelfmark -- not which of the',
                  '> {} records is which scan. Treat the coverage as likely, not established.'.format(n),
                  '']
        L.append('')
    L.append('---')
    for sig in sorted(by, key=lambda s: (-len(by[s]), s)):
        rs = by[sig]
        inst = rs[0]['institution'] or ''
        iid = rs[0]['institution_id']
        h_got = sum(bool(r['got']) for r in rs)
        head = (f"## {sig} — {inst} ({len(rs)}"
                + (f', {h_got} held' if h_got else '') + ')')
        L += ['', head, '']
        if iid:
            L.append(f'RISM library page: <{BASE}/{iid}>')
            L.append('')
        L += ['| G | title | shelfmark | type | parts | plate | date | incipits | source | got |',
              '|---|---|---|---|---|---|---|---|---|---|']
        for r in sorted(rs, key=lambda r: (bool(r['got']), gnum(r['gerard']), r['source_id'])):
            L.append('| {} | {} | {} | {} | {} | {} | {} | {} | [{}]({}) | {} |'.format(
                cell(r['gerard']), cell((r['title'] or '')[:22]),
                cell((r['shelfmark'] or '')[:26]),
                cell((r['source_type'] or '') + (' **AUTOGRAPH**' if r['is_autograph'] else '')),
                cell(r['extent']), cell(r['plate']), cell(r['date']),
                r['incipits'], r['source_id'], r['source'],
                r['got_s']))
    (outdir / 'UNLINKED-HOLDINGS.md').write_text('\n'.join(L))
    return tot, len(by), have


def index(recs, outdir):
    """INDEX.md: what we have, by G number, including what we could not fetch."""
    by = {}
    for r in recs: by.setdefault(r['meta']['gerard'], []).append(r)
    L = ['# Boccherini string-quartet digitizations',
         '', f'Harvested from RISM Online. {len(recs)} MARC 856 links over '
             f"{len({r['meta']['source_id'] for r in recs})} quartet sources.",
         '', 'Kinds: **iiif** / **image** are direct downloads; **digitized** is a library',
         'landing page reached through a resolver; **other** is catalogue matter, not music.',
         '']
    t = {k: sum(r['kind'] == k for r in recs) for k in KINDS}
    L += [f"`{k}` {v}" for k, v in t.items() if v]
    L += ['', '---', '']
    for g in sorted(by, key=gnum):
        rs = by[g]
        L.append(f"## {'G ' + g if g else 'No Gérard number in RISM'}"
                 + (f'  — `{gdir(g)}/`' if g else '  — `unidentified/`'))
        m0 = rs[0]['meta']
        L.append('')
        L.append(f"*{m0['title'] or ''}* — {m0['scoring'] or ''}"
                 + (f" · {', '.join(m0['catalogs'][:3])}" if m0['catalogs'] else ''))
        L += ['', '| source | held at | type | parts | plate | published | link | got |',
              '|---|---|---|---|---|---|---|---|']
        for r in sorted(rs, key=lambda r: (KINDS.index(r['kind']), r['meta']['source_id'])):
            m = r['meta']
            p = m['published']
            L.append('| [{}]({}) | {} | {} | {} | {} | {} | {} | {} |'.format(
                m['source_id'], m['source'],
                cell(' '.join(filter(None, (r['siglum'], r['shelfmark'])))
                     or (', '.join(r['all_sigla'][:4]) + ('…' if len(r['all_sigla']) > 4 else ''))),
                cell((r['source_type'] or ', '.join(m['source_types']))
                     + (' **(autograph)**' if m['is_autograph'] else '')),
                cell(r['holding_extent'] or ', '.join(m['extent'])),
                cell(', '.join(m['plate_numbers'])),
                cell(' '.join(filter(None, (p['publisher'], p['date'])))),
                f"`{r['kind']}`{' watermark' if is_watermark(r) else ''} [link]({r['url']})",
                (f"{len(r['files'])} files" + (' ⚠ check' if r.get('label_unverified') else ''))
                if r.get('files') else
                ('no pages published' if r.get('no_pages') else
                 '**manual**' if r.get('unresolved') else '—')))
        L.append('')
    (outdir / 'INDEX.md').write_text('\n'.join(L))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--name', default='Boccherini, Luigi')
    p.add_argument('--person', help='RISM person id; skips name lookup')
    p.add_argument('--q', default='Quartets', help="server-side keyword prefilter; '' to disable")
    p.add_argument('--fq', action='append', default=[], help='server-side facet filter; repeatable')
    p.add_argument('--all', action='store_true', help='skip the local quartet filter')
    p.add_argument('--kind', action='append', choices=KINDS, help='keep only these; repeatable')
    p.add_argument('--g', action='append', help='keep only these Gerard numbers; repeatable')
    p.add_argument('--no-incipits', action='store_true',
                   help='only sources RISM has no incipit for -- the transcription targets')
    p.add_argument('--download', action='store_true', help='fetch, and write INDEX.md')
    p.add_argument('--full', action='store_true', help='full resolution; tiles where a server caps')
    p.add_argument('--pages', type=int, default=0, help='cap pages per source (0 = all)')
    p.add_argument('--out', type=Path, default=Path('digitizations'))
    p.add_argument('--cache', type=Path, default=Path('.rism-cache'))
    p.add_argument('-j', type=int, default=4)
    a = p.parse_args()

    a.cache.mkdir(exist_ok=True)
    cache_dir[0] = a.cache
    pid = a.person or person(a.name)
    ids = sources(pid, a.q, a.fq)
    print(f'person {pid}: {len(ids)} sources', file=sys.stderr)
    with ThreadPoolExecutor(a.j) as ex:
        out = [r for rs in ex.map(lambda s: rows(s, a.cache, a.all, pid), ids) for r in rs]
    if a.kind: out = [r for r in out if r['kind'] in a.kind]
    if a.g: out = [r for r in out if r['meta']['gerard'] in a.g]
    if a.no_incipits: out = [r for r in out if not r['meta']['incipits']]
    out.sort(key=lambda r: (gnum(r['meta']['gerard']), r['meta']['source_id'], KINDS.index(r['kind'])))

    t = {k: sum(r['kind'] == k for r in out) for k in KINDS}
    print(f"{len(out)} links over {len({r['meta']['source_id'] for r in out})} sources; "
          + ', '.join(f'{v} {k}' for k, v in t.items() if v), file=sys.stderr)
    if a.download:
        a.out.mkdir(parents=True, exist_ok=True)
        n = download(out, a.out, a.full, a.pages, load_resolved(a.cache))
        with open(a.out / 'inventory.jsonl', 'w') as f:
            for r in out:
                f.write(json.dumps({k: v for k, v in r.items() if k != 'meta'} | r['meta'],
                                   ensure_ascii=False) + '\n')
        index(out, a.out)
        mn = manual_list(out, a.out)
        with ThreadPoolExecutor(a.j) as ex:
            ul = [r for rs in ex.map(lambda s: unlinked_rows(s, a.cache, a.all, pid), ids) for r in rs]
        uh, ui, ug = unlinked_file(ul, a.out)
        print(f'{n} new files -> {a.out}/\n'
              f'  INDEX.md, inventory.jsonl\n'
              f'  MANUAL-DOWNLOADS.md    {mn} items a script cannot reach\n'
              f'  UNLINKED-HOLDINGS.md   {uh} holdings at {ui} libraries with no RISM scan link'
              f' ({ug} of them held anyway)',
              file=sys.stderr)
    else:
        for r in out:
            print(json.dumps({k: v for k, v in r.items() if k != 'meta'} | r['meta'], ensure_ascii=False))
