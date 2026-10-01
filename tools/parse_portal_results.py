# /// script
# requires-python = ">=3.11"
# ///
"""Read a saved portal search page and pull out the Boccherini items worth having.

    uv run tools/parse_portal_results.py ~/Downloads/*.html
    uv run tools/parse_portal_results.py --all ~/Downloads/page.html     # don't filter to quartets

BNE Digital and the Staatsbibliothek both sit behind Cloudflare or a JavaScript front end,
so neither can be fetched from a script -- `curl` gets a bot challenge, not results. What a
browser has already rendered can be saved to disk, and that is what this reads.

Writes `digitizations/PORTAL-FINDS.md`: every item, classified the same way as the Gallica
search, with quartets separated from the quintets and symphonies that dominate both
holdings. Anything worth downloading can then be declared in `corrections.json` under
`found_by_hand` so it gets a folder and sidecars like any other item.
"""
import argparse, html, json, re, sys, time, urllib.request
from pathlib import Path

SBB = 'https://content.staatsbibliothek-berlin.de/dc'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
# Berlin puts the Gerard number straight in its titles -- 'G 183; op.22,1', 'G 201-206' --
# so unlike the Gallica finds these need no hand identification.
GERARD = re.compile(r'\bG\s*(\d{1,3})(?:\s*-\s*(\d{1,3}))?\b')

# Same vocabulary as find_scans.py: Boccherini's quartets appear as Quartetti, Quartettini,
# Divertimenti and 'Sinfonie o quartetti', and 'quatuor' also labels wind arrangements.
FOUR_PART = re.compile(r'quartett|quatuor|quartet|cuarteto|divertiment', re.I)
QUINTET = re.compile(r'quintett|quintuor|quintet|quinteto|sestett|sextuor', re.I)
TRIO = re.compile(r'terzett|\btrio\b|\btrii\b', re.I)
WEAK = re.compile(r'sonat|sinfoni|symphon', re.I)
FOUR_STRINGS = re.compile(r'(?=.*violin|.*violon)(?=.*(?:viola|alto|violetta|taille))'
                          r'(?=.*(?:violoncell|basso|basse|\bcello\b|\bbass\b))', re.I | re.S)
NOT_STRINGS = re.compile(r'fl[aeuû]t|clarinet|basson|fagott|\bcorni?\b|hautbois|oboe|guitar|'
                         r'piano|clavecin|forte.?piano|harpe|chant|voix|orchestr', re.I)
AUTOGRAPH = re.compile(r'autograph|autógrafo', re.I)
MANUSCRIPT = re.compile(r'manuscri|handwritten|manuscrito|\bMS\b|Mus\.ms', re.I)
YEAR = re.compile(r'\b(1[678]\d\d)\b')
# Every BNE row carries the creator's dates -- 'Boccherini, Luigi (1743-1805)' -- so the
# first four-digit year in the text is his birth, not the edition's.
LIFESPAN = re.compile(r'\(\s*1[678]\d\d\s*[-–]\s*1[678]\d\d\s*\)')


def classify(text):
    form = ('quintet' if QUINTET.search(text) else 'trio' if TRIO.search(text) else
            'quartet' if FOUR_PART.search(text) else
            'quartet?' if WEAK.search(text) and FOUR_STRINGS.search(text) else 'other')
    medium = ('autograph' if AUTOGRAPH.search(text) else
              'manuscript' if MANUSCRIPT.search(text) else 'print')
    return form, medium, not NOT_STRINGS.search(text)


def strip(frag):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', frag))).strip()


def parse_bne(s):
    """BNE Digital renders each hit as an <article> with a UUID viewer link."""
    out = []
    for a in re.findall(r'<article.*?</article>', s, re.S):
        vid = re.search(r'/viewer\?id=([0-9a-f-]{36})', a)
        if not vid: continue
        t = strip(a)
        t = re.sub(r'\s*(See the work|Details|Add to my BNE Digital|Eliminar.*|Add)\s*$', '', t)
        out.append(dict(portal='BNE', ident=vid[1], title=t[:300],
                        url=f'https://bnedigital.bne.es/bd/es/viewer?id={vid[1]}&page=1',
                        card=f'https://bnedigital.bne.es/bd/es/card?id={vid[1]}'))
    return out


def parse_sbb(s):
    """Staatsbibliothek results: one `div.row.search-result` per hit.

    Each result is wrapped in an <a> that itself contains a nested preview <a>, so splitting
    on the werkansicht anchors cuts every title off after the composer's name."""
    out, seen = [], set()
    blocks = re.split(r'(?=<div class="row search-result)', s)
    for b in blocks[1:]:
        ppn = re.search(r'PPN=(PPN\d+)', b) or re.search(r'/dms/(PPN\d+)/', b)
        if not ppn or ppn[1] in seen: continue
        seen.add(ppn[1])
        t = strip(b)
        # Drop the leading breadcrumb/creator that precedes every title.
        t = re.sub(r'^[\s>]*Boccherini,\s*Luigi\s*', '', t)
        if not t: continue
        out.append(dict(portal='SBB', ident=ppn[1], title=t[:300],
                        url=f'https://digital-beta.staatsbibliothek-berlin.de/werkansicht?PPN={ppn[1]}',
                        card=f'https://content.staatsbibliothek-berlin.de/dc/{ppn[1]}.mets.xml'))
    return out


def parse(path):
    s = Path(path).read_text(encoding='utf8', errors='replace')
    if 'bnedigital.bne.es' in s: items = parse_bne(s)
    elif 'staatsbibliothek-berlin' in s: items = parse_sbb(s)
    else:
        print(f'  ? {Path(path).name}: not a BNE or SBB results page', file=sys.stderr)
        return []
    for it in items:
        it['form'], it['medium'], it['strings'] = classify(it['title'])
        yrs = YEAR.findall(LIFESPAN.sub(' ', it['title']))
        it['year'] = yrs[0] if yrs else None
    return items


def fetch(url, tries=4, timeout=90):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(r, timeout=timeout).read()
        except Exception:
            if i == tries - 1: raise
            time.sleep(2 ** i)


def gerard_of(title):
    """['183'] or ['201'..'206'] from a Berlin title, or [] if it names none."""
    m = GERARD.search(title)
    if not m: return []
    lo = int(m[1])
    hi = int(m[2]) if m[2] else lo
    return [str(n) for n in range(lo, hi + 1)] if 0 < hi - lo < 24 else [str(lo)]


def glabel(nums):
    if not nums: return None
    if len(nums) == 1: return nums[0]
    return f'{nums[0]}-{nums[-1]}' if int(nums[-1]) - int(nums[0]) == len(nums) - 1 else ', '.join(nums)


def canvases(manifest):
    d = json.loads(manifest)
    s_ = d.get('sequences')
    cs = (s_[0].get('canvases', []) if s_ else d.get('items', []))
    out = []
    for c in cs:
        im = (c.get('images') or [{}])[0].get('resource', {})
        svc = im.get('service') or {}
        if isinstance(svc, list): svc = svc[0] if svc else {}
        out.append((svc.get('@id') or svc.get('id'), im.get('@id')))
    return out


def volumes(ppn):
    """[(ppn, label)] — a MultivolumeWork anchor serves an empty manifest; its scans live on
    the child volumes listed in its METS. Reading the empty manifest as 'not digitized' is
    what hid Berlin's Op. 58 from this project for a whole session."""
    try:
        cs = canvases(fetch(f'{SBB}/{ppn}/manifest'))
    except Exception as e:
        print(f'  ! {ppn}: {e}', file=sys.stderr)
        return []
    if cs: return [(ppn, None)]
    try:
        mets = fetch(f'{SBB}/{ppn}.mets.xml').decode('utf8', 'replace')
    except Exception:
        return []
    if 'MultivolumeWork' not in mets: return []
    kids = [k for k in dict.fromkeys(re.findall(r'PPN\d+', mets)) if k != ppn]
    out = []
    for k in kids:
        try:
            m = fetch(f'{SBB}/{k}.mets.xml').decode('utf8', 'replace')
        except Exception:
            continue
        lab = (re.findall(r'<[^>]*:number[^>]*>([^<]{1,40})</[^>]*:number>', m) or [None])[0]
        out.append((k, lab))
        time.sleep(.3)
    print(f'  {ppn} is an anchor — {len(out)} volume(s)', file=sys.stderr)
    return out


def already_have(root):
    """PPNs already on disk, from IIIF manifests and from corrections.json.

    Berlin's search surfaces the same manuscripts RISM already links, just found from the
    other end: of 44 quartets in one saved page, 34 were items this project had downloaded
    through RISM. Hand-downloaded items carry no manifest, so corrections.json has to be
    read too."""
    have = {}
    for f in Path(root).glob('*/*/manifest.json'):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        m = re.search(r'/dc/(\d{6,})', str(d.get('@id') or d.get('id') or ''))
        if m: have[m[1]] = f.parent
    try:
        txt = Path('corrections.json').read_text()
        for m in re.finditer(r'PPN(\d{6,})', txt):
            have.setdefault(m[1], Path('corrections.json'))
    except Exception:
        pass
    return have


def grab_sbb(it, root, limit=0, have=None):
    """Download one Berlin item (following anchors) into its Gerard folder.

    The dedup has to be applied to each *volume*, not just the item: an anchor's children are
    separate PPNs, and one of them was already here as a hand download."""
    have = have or {}
    nums = gerard_of(it['title'])
    gdir = 'G' + (glabel(nums) or '').replace(', ', '_') if nums else 'unidentified'
    n = 0
    for ppn, vol in volumes(it['ident']):
        d_have = have.get(ppn.replace('PPN', ''))
        if d_have is not None and not str(getattr(d_have, 'name', '')).startswith(ppn):
            print(f'  = {ppn} already held ({d_have})', file=sys.stderr)
            continue
        name = f"{ppn}_D-B" + (f"_{re.sub(r'[^a-z0-9]+', '', (vol or '').lower())}" if vol else '')
        d = Path(root) / gdir / name
        d.mkdir(parents=True, exist_ok=True)
        mf = d / 'manifest.json'
        if not mf.exists(): mf.write_bytes(fetch(f'{SBB}/{ppn}/manifest'))
        cs = canvases(mf.read_bytes())
        d.joinpath('metadata.json').write_text(json.dumps(
            dict(source='sbb', portal='SBB', ppn=ppn, volume=vol, siglum='D-B',
                 title=it['title'], gerard=nums[0] if nums else None,
                 gerard_numbers=nums, gerard_label=glabel(nums),
                 medium=it['medium'], form=it['form'], year=it['year'],
                 url=f"https://digital-beta.staatsbibliothek-berlin.de/werkansicht?PPN={ppn}",
                 mets=f'{SBB}/{ppn}.mets.xml', pages=len(cs),
                 found_by_hand=False, found_via='saved SBB search page'),
            ensure_ascii=False, indent=1))
        d.joinpath('README.md').write_text(
            f"# {it['title'][:120]}\n\nFound in a saved Staatsbibliothek search page, **not linked "
            f"by RISM**.\n\n- **Gérard:** {glabel(nums) or 'not stated in the title'}\n"
            f"- **Volume:** {vol or '—'}\n- **Medium:** {it['medium']}\n- **Pages:** {len(cs)}\n"
            f"- **Viewer:** <https://digital-beta.staatsbibliothek-berlin.de/werkansicht?PPN={ppn}>\n"
            f"- **METS:** <{SBB}/{ppn}.mets.xml>\n")
        print(f"  {gdir}/{name}: {len(cs)} pages — {it['title'][:52]}", file=sys.stderr)
        for i, (svc, direct) in enumerate(cs, 1):
            if limit and i > limit: break
            f = d / f'{i:03d}.jpg'
            if f.exists() and f.stat().st_size: continue
            try:
                f.write_bytes(fetch(f'{svc}/full/max/0/default.jpg' if svc else direct))
                n += 1
            except Exception as e:
                print(f'    ! page {i}: {e}', file=sys.stderr)
            time.sleep(.15)
    return n


def stage(items, root, portal):
    """Folders and a checklist for items only a browser can fetch.

    Status is read off disk every time rather than tracked by hand: a folder outside
    `unidentified/` means the item has been identified and filed, a folder with a file in it
    means it has been downloaded. So the checklist cannot drift from reality."""
    rows = [i for i in items if i['portal'] == portal and i['form'].startswith('quartet')
            and i['strings']]
    root = Path(root)

    def state(ident):
        """(status, folder, gerard-label) for one portal item, from disk.

        A folder can also carry `skipped: true` -- a decision not to download it, which is
        as settled as having it, and should stop showing up on the worklist."""
        name = f"{portal.lower()}-{ident[:12]}"
        for d in root.glob(f'*/{name}'):
            try:
                meta = json.loads((d / 'metadata.json').read_text())
            except Exception:
                meta = {}
            if meta.get('skipped'): return 'skipped', d, meta.get('skip_reason')
            has = any(f.suffix.lower() in ('.pdf', '.jpg', '.jpeg', '.png') for f in d.iterdir())
            if not has: return 'todo', d, None
            if d.parent.name == 'unidentified':
                return 'downloaded', d, None
            g = None
            try:
                g = json.loads((d / 'metadata.json').read_text()).get('gerard_label')
            except Exception:
                pass
            return 'filed', d, g
        return 'todo', root / 'unidentified' / name, None

    st = {i['ident']: state(i['ident']) for i in rows}
    done = [i for i in rows if st[i['ident']][0] == 'filed']
    dl = [i for i in rows if st[i['ident']][0] == 'downloaded']
    todo = [i for i in rows if st[i['ident']][0] == 'todo']
    skip = [i for i in rows if st[i['ident']][0] == 'skipped']

    def clean(t):
        return re.sub(r'^\s*Notated [Mm]usic / (?:Printed Music|Handwritten music)\s*', '', t)

    L = [f'# {portal}: quartets to download by hand', '',
         f'{len(rows)} printed or manuscript quartets found in the saved search page. '
         f'{portal} cannot be fetched by a script, so each one needs a click.', '',
         '| | |', '|---|---:|',
         f'| **Still to download** | **{len(todo)}** |',
         f'| Downloaded, not yet identified | {len(dl)} |',
         f'| Identified and filed | {len(done)} |']
    if skip:
        L.append(f'| Deliberately skipped | {len(skip)} |')
    L.append('')

    if todo:
        L += ['---', '', '## Still to download', '',
              'Each has a folder waiting with its `metadata.json` — save the download into it '
              'and the shelf picks it up.', '']
        for i in sorted(todo, key=lambda r: (r['year'] or '9999', r['title'])):
            _, d, _ = st[i['ident']]
            want = f"{portal}_{i['ident'][:12]}.pdf"
            L += [f"### {i['year'] or '—'} · {clean(i['title'])[:88]}", '',
                  f"[**Download**]({i['url']})"
                  + (f" · [record]({i['card']})" if i.get('card') else ''),
                  '', f"`{d}/{want}`", '']

    if dl:
        L += ['---', '', '## Downloaded — needs identifying', '',
              'The scan is on disk but nobody has said which works are in it. Open it, read the '
              'title page, and the Gérard numbers can be recorded.', '']
        for i in sorted(dl, key=lambda r: (r['year'] or '9999', r['title'])):
            _, d, _ = st[i['ident']]
            L += [f"- **{i['year'] or '—'}** · {clean(i['title'])[:96]}",
                  f"  `{d}` · [view]({i['url']})"]
        L.append('')

    if done:
        L += ['---', '', '## Identified and filed', '', '| year | Gérard | edition | folder |',
              '|---|---|---|---|']
        for i in sorted(done, key=lambda r: st[r['ident']][2] or ''):
            _, d, g = st[i['ident']]
            L.append(f"| {i['year'] or '—'} | **G {g or '?'}** | "
                     f"{clean(i['title'])[:60].replace('|', chr(92) + '|')} | `{d.name}` |")
        L.append('')

    if skip:
        L += ['---', '', '## Deliberately skipped', '',
              'Decided against, not overlooked — listed so they are not re-found later.', '',
              '| year | item | why |', '|---|---|---|']
        for i in sorted(skip, key=lambda r: (r['year'] or '9999', r['title'])):
            why = (st[i['ident']][2] or '').replace('|', chr(92) + '|')
            L.append(f"| {i['year'] or '—'} | {clean(i['title'])[:52].replace('|', chr(92) + '|')} "
                     f"| {why} |")
        L.append('')

    Path(root, f'{portal}-TODO.md').write_text('\n'.join(L))
    return len(todo)


def report(items, out):
    order = {'quartet': 0, 'quartet?': 1, 'quintet': 2, 'trio': 3, 'other': 4}
    L = ['# Boccherini at BNE Digital and the Staatsbibliothek',
         '', 'Read from search pages saved out of a browser: neither portal can be fetched by a',
         'script — BNE answers `curl` with a Cloudflare challenge and the Staatsbibliothek',
         'search is a JavaScript front end. Form and medium are read off each title, so treat',
         'them as strong hints rather than facts.',
         '']
    tot = {}
    for it in items: tot[(it['portal'], it['form'])] = tot.get((it['portal'], it['form']), 0) + 1
    ports = sorted({i['portal'] for i in items})
    L += ['| form | ' + ' | '.join(ports) + ' |', '|---|' + '---:|' * len(ports)]
    for f in sorted({i['form'] for i in items}, key=lambda f: order.get(f, 9)):
        L.append(f'| {f} | ' + ' | '.join(str(tot.get((p, f), 0)) for p in ports) + ' |')
    L.append('')
    for f in sorted({i['form'] for i in items}, key=lambda f: order.get(f, 9)):
        rows = [i for i in items if i['form'] == f]
        head = {'quartet': 'Quartets', 'quartet?': 'Probably quartets — verify',
                'quintet': 'Quintets and larger', 'trio': 'Trios'}.get(f, 'Everything else')
        L += ['---', '', f'## {head} ({len(rows)})', '']
        if f.startswith('quartet'):
            L.append('These are the ones worth downloading. Arrangements for winds or keyboard '
                     'are marked, and are not string quartets.')
            L.append('')
        L += ['| portal | medium | year | title | link |', '|---|---|---|---|---|']
        for it in sorted(rows, key=lambda i: (i['portal'], i['year'] or '', i['title'])):
            L.append(f"| {it['portal']} | {'**' + it['medium'] + '**' if it['medium'] != 'print' else it['medium']}"
                     f"{'' if it['strings'] else ' · arrangement'} | {it['year'] or '—'} "
                     f"| {it['title'][:96].replace('|', chr(92) + '|')} "
                     f"| [{it['ident'][:12]}]({it['url']}) |")
        L.append('')
    Path(out).write_text('\n'.join(L))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('files', nargs='+', type=Path)
    p.add_argument('--all', action='store_true', help='report every form, not just quartets')
    p.add_argument('--out', type=Path, default=Path('digitizations/PORTAL-FINDS.md'))
    p.add_argument('--json', type=Path, help='also write the items as JSON')
    p.add_argument('--download', action='store_true',
                   help='fetch the Staatsbibliothek quartets (its IIIF server is scriptable)')
    p.add_argument('--root', type=Path, default=Path('digitizations'))
    p.add_argument('--pages', type=int, default=0, help='cap pages per volume (0 = all)')
    p.add_argument('--stage', action='append', metavar='PORTAL',
                   help='make folders + a checklist for a portal only a browser can fetch')
    a = p.parse_args()

    items = [i for f in a.files for i in parse(f)]
    seen, uniq = set(), []
    for i in items:
        if i['ident'] in seen: continue
        seen.add(i['ident']); uniq.append(i)
    q = [i for i in uniq if i['form'].startswith('quartet')]
    print(f'{len(uniq)} items parsed — {len(q)} quartets '
          f'({sum(1 for i in q if i["medium"] == "autograph")} autograph, '
          f'{sum(1 for i in q if i["medium"] == "manuscript")} manuscript)', file=sys.stderr)
    for p_ in sorted({i['portal'] for i in uniq}):
        n = [i for i in uniq if i['portal'] == p_]
        print(f'   {p_}: {len(n)} items, {sum(1 for i in n if i["form"].startswith("quartet"))} quartets',
              file=sys.stderr)
    if a.download:
        have = already_have(a.root)
        cand = [i for i in uniq if i['portal'] == 'SBB' and i['form'].startswith('quartet')
                and i['strings']]
        # Skip only what is held *elsewhere*. An item's own folder being present means a
        # previous run was interrupted, and grab_sbb resumes it page by page -- deduping on
        # that would freeze four items a page or two short of complete.
        def held_elsewhere(i):
            d = have.get(i['ident'].replace('PPN', ''))
            return d is not None and not str(d.name).startswith(i['ident'])
        todo = [i for i in cand if held_elsewhere(i) is False]
        skip = len(cand) - len(todo)
        print(f'{len(cand)} Berlin quartets: {skip} already held, downloading {len(todo)}',
              file=sys.stderr)
        got = sum(grab_sbb(i, a.root, a.pages, have) for i in todo)
        print(f'{got} new pages', file=sys.stderr)
    for portal in (a.stage or []):
        n = stage(uniq, a.root, portal)
        print(f'staged {n} {portal} items -> {a.root}/{portal}-TODO.md', file=sys.stderr)
    report(uniq, a.out)
    if a.json: a.json.write_text(json.dumps(uniq, ensure_ascii=False, indent=1))
    print(f'-> {a.out}', file=sys.stderr)
