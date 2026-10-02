# /// script
# requires-python = ">=3.11"
# ///
"""Match a citation to a RISM source, and say whether we hold a scan of it.

A citation in a book or an article names a source in whatever way its author found
convenient: `F-Po Rés. 507 (14)`, `Berlin, Mus.ms. 2005/2`, `RISM 840013721`, `G 228`,
`op. 48 no. 3`, `PPN847531627`. All of those point at the same kind of thing, and none of
them is the handle this archive files by. This builds the crosswalk.

    uv run tools/concordance.py                        # build the tables
    uv run tools/concordance.py --match "F-Po RES-507 (14)"
    uv run tools/concordance.py --match-file notes.md  # every citation it can find in a document

Writes `concordance.jsonl` (one row per RISM source, every handle it has) and
`digitizations/CONCORDANCE.md` (the same, readable, indexed by library and by Gérard).

Scoring is deliberately blunt: a siglum plus a shelfmark is near-conclusive and scores 100,
a RISM id is conclusive and scores 120, a Gérard number alone is suggestive and scores 20 —
because a Gérard number usually matches a dozen sources and the point is to show you all of
them, not to pick one. Nothing here decides; it ranks.
"""
import argparse, importlib.util, json, re, sys, collections, unicodedata
import evidence
from pathlib import Path

spec = importlib.util.spec_from_file_location('rd', 'tools/rism_digitizations.py')
rd = importlib.util.module_from_spec(spec); spec.loader.exec_module(rd)
CACHE = Path('.rism-cache'); rd.cache_dir[0] = CACHE
DIG = Path('digitizations')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')

SIGLUM = re.compile(r'\b([A-Z]{1,2}-[A-Za-z][A-Za-z]{0,9})\b')
RISMID = re.compile(r'\b(\d{6,9})\b')
GERARD = re.compile(r'\b(?:G|GerB|Gér(?:ard)?)\.?\s*(\d{1,3})\b', re.I)
OPUSNO = re.compile(r'\bop(?:us|\.)?\s*(\d{1,2})\s*(?:[,/]|\bno?\.?\s*|\bn\.?\s*)\s*(\d)\b', re.I)
OPUS = re.compile(r'\bop(?:us|\.)?\s*(\d{1,2})\b', re.I)
PPN = re.compile(r'\b(PPN[0-9X]{6,})\b')
ARK = re.compile(r'\b(ark:/12148/[a-z0-9]+)\b')


def flat(s):
    """Fold to letters and digits, accents removed -- a citation writes 'Rés. 507 (14)'
    where RISM writes 'RES-507 (14)'."""
    s = unicodedata.normalize('NFKD', s or '')
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in s if not unicodedata.combining(c)).lower())


def walk_urls(v, out=None):
    """Every RISM source URL inside a string, list or dict."""
    out = [] if out is None else out
    if isinstance(v, str):
        if '/sources/' in v: out.append(v)
    elif isinstance(v, list):
        for x in v: walk_urls(x, out)
    elif isinstance(v, dict):
        for x in v.values(): walk_urls(x, out)
    return out


def norm(s):
    """A shelfmark as a join key, or '' when it cannot be one.

    RISM writes '[no indication]' wherever a shelfmark is unknown. Keying on that makes
    every shelfmark-less holding at a library collapse into one, and a match to any of them
    matches all of them -- which is how Rochester's folders were briefly credited to
    Madrid's shelfmark. No real shelfmark in this corpus lacks a digit, so requiring one
    costs nothing and closes it."""
    n = flat(s)
    return n if any(c.isdigit() for c in n) else ''


def spine():
    """gerard -> (opus, number, key, year) from opera.json, the authoritative list."""
    out, groups = {}, []

    def walk(x):
        if isinstance(x, dict):
            if 'opus' in x and 'quartets' in x: groups.append(x)
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(json.loads(Path('opera.json').read_text()))
    for g in groups:
        for q in g['quartets']:
            out[str(q.get('gerard'))] = (g.get('opus'), q.get('number'), q.get('key'), g.get('year'))
    return out


def held():
    """What is on disk, indexed three ways, in decreasing order of trust.

      shelf    (siglum, normalised shelfmark) -> folders. Useful, but a shelfmark is not
               always one object: D-B `DMS 51778` covers ten of our folders, so a shelfmark
               match alone once reported Pleyel's oeuvre 39 as held at Op. 9 and Op. 15.
      by_rism  RISM id -> folders that explicitly say they are a copy of it. Definitive
               about the source, not about which library's copy: see `placed`.
      claims   folder -> the ids it claims, so a shelfmark match can be refused when the
               folder is demonstrably a copy of something else.
      own      folder -> the ids it was harvested as (`source_id`, `source`), as opposed to
               ones someone linked it to afterwards.
      where    folder -> (siglum, shelfmark as written).
    """
    shelf, claims, own, where = collections.defaultdict(set), {}, {}, {}
    for p in DIG.rglob('metadata.json'):
        d = p.parent
        if not any(f.suffix.lower() in MEDIA for f in d.iterdir() if f.is_file()): continue
        try:
            m = json.loads(p.read_text())
        except Exception:
            continue
        rel = str(d.relative_to(DIG))
        where[rel] = (m.get('siglum'), m.get('shelfmark'))
        if m.get('siglum') and norm(m.get('shelfmark')):
            shelf[(m['siglum'], norm(m['shelfmark']))].add(rel)
        ids = set()
        if m.get('source_id'): ids.add(str(m['source_id']))
        for u in walk_urls(m.get('source')): ids.add(u.rstrip('/').rsplit('/', 1)[-1])
        own[rel] = set(ids)
        # A 'work' link points at RISM's record for the edition at another library. It is
        # not a claim to be a copy of it, so it must not answer "do we hold this source".
        if m.get('rism_relation') != 'work':
            for k in ('rism_related', 'rism_constituents'):
                for u in walk_urls(m.get(k)): ids.add(u.rstrip('/').rsplit('/', 1)[-1])
        claims[rel] = ids
    by_rism = collections.defaultdict(set)
    for rel, ids in claims.items():
        for i in ids: by_rism[i].add(rel)
    return shelf, by_rism, claims, own, where


def folder_state():
    """folder -> (tier, label). What stands behind each held item's label."""
    out = {}
    for p in DIG.rglob('metadata.json'):
        d = p.parent
        if not any(f.suffix.lower() in MEDIA for f in d.iterdir() if f.is_file()): continue
        try:
            m = json.loads(p.read_text())
        except Exception:
            continue
        out[str(d.relative_to(DIG))] = evidence.tier_of(m, evidence.reading(d.name))
    return out


def editions():
    """RISM id -> folders holding the same edition at a shelfmark RISM does not record.

    Kept apart from `by_rism` on purpose: these are not copies of that source. But someone
    looking up a RISM record wants to know the edition is on disk even when the copy we
    have is a different library's, so the answer must be 'a copy of this edition, not this
    copy' rather than silence. 34 folders are reachable only this way -- every BnF print
    RISM catalogues without a shelfmark, and Pleyel's oeuvre 39 livraisons."""
    out = collections.defaultdict(set)
    for p in DIG.rglob('metadata.json'):
        d = p.parent
        if not any(f.suffix.lower() in MEDIA for f in d.iterdir() if f.is_file()): continue
        try:
            m = json.loads(p.read_text())
        except Exception:
            continue
        if m.get('rism_relation') != 'work': continue
        for u in walk_urls(m.get('rism_related')):
            out[u.rstrip('/').rsplit('/', 1)[-1]].add(str(d.relative_to(DIG)))
    return out


RANGE = re.compile(r'\(\s*(\d+)\s*-\s*(\d+)\s*\)\s*$')


def tokens(s):
    """A shelfmark as (tokens, item range or None). RISM gives the six quartets of F-Pn
    `Vma ms 1067` one holding, `VMA MS-1067 (1-6)`, where our folders say `(2)`; flattened
    to a string, `(1)` is a prefix of `(1-6)` and of `(10)` alike, so compare by token."""
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    r = RANGE.search(s)
    rng = (int(r.group(1)), int(r.group(2))) if r else None
    t = re.findall(r'\d+|[a-z]+', RANGE.sub('', s) if r else s)
    return (t, rng) if any(x.isdigit() for x in t) or rng else ([], None)


def same_shelf(a, b):
    """Whether shelfmarks `a` and `b` can name the same object: equal, one an item of the
    other's range, or one the volume the other is an item of. Unknown on either side is
    not a contradiction."""
    (ta, ra), (tb, rb) = tokens(a), tokens(b)
    if not ta or not tb: return True
    if (ta, ra) == (tb, rb): return True
    for (t1, r1), (t2, r2) in (((ta, ra), (tb, rb)), ((tb, rb), (ta, ra))):
        if r2 and not r1 and t1[:-1] == t2 and t1[-1].isdigit() and r2[0] <= int(t1[-1]) <= r2[1]:
            return True
        if not r1 and not r2 and len(t1) < len(t2) and t2[:len(t1)] == t1:
            return True
    return False


def placed(sid, holdings, by_rism, own, where):
    """holding index -> the folders that are a copy of that holding.

    A print record lists every library with a copy, and a claim to be "a copy of
    990005874" says nothing about which of its twelve: credited to all of them, one
    Rochester scan stood in for eleven other libraries. So a claim lands only on a holding
    at the folder's own library, and a shelfmark that contradicts it refuses it. The one
    exception is the record a folder was harvested as -- the portal said this is that
    copy -- which lands on its library's holding even when RISM shelves it as the whole
    volume. A claim that lands nowhere is left to `boc check`, which names it."""
    out = collections.defaultdict(list)
    for f in sorted(by_rism.get(sid, set())):
        fs, fk = where.get(f, (None, None))
        here = [i for i, h in enumerate(holdings) if h['siglum'] == fs]
        fit = [i for i in here if same_shelf(fk, holdings[i].get('shelfmark'))]
        if not fit and sid in own.get(f, ()) and len(here) == 1:
            fit = here
        if len(fit) > 1:
            # one scan is one copy: two holdings at one library, and nothing to choose
            # between them, is not two copies held
            exact = [i for i in fit if tokens(holdings[i].get('shelfmark')) == tokens(fk)]
            fit = exact if len(exact) == 1 else []
        for i in fit:
            out[i].append(f)
    return out


def held_for(sid, siglum, shelfmark, shelf, claims, where, direct):
    """(folders, how) for one holding: the copies of it we actually have.

    Falls back from an explicit claim, to the same shelfmark, to a shelfmark this one
    extends -- RISM catalogues the six quartets inside D-B `KHM 577` as `KHM 577 (1)` …
    `(6)`, and we hold the volume, so a lookup for a constituent should find it.
    `direct` is what `placed` put on this holding."""
    if direct:
        return direct, 'copy'
    if not siglum or not norm(shelfmark):
        return [], None

    def free(f):
        """A folder that claims nothing, or claims this very source."""
        return not claims.get(f) or sid in claims[f]

    k = norm(shelfmark)
    exact = sorted(f for f in shelf.get((siglum, k), set()) if free(f))
    if exact:
        return exact, 'shelfmark'
    # No `free` test here: a parent volume necessarily claims a different source -- the
    # volume's own record -- and that is exactly what makes it the parent. The guard is
    # that the shelfmark must be a strict extension by whole tokens, so `KHM 577 (1)`
    # finds `KHM 577` while ten folders sharing the blanket `DMS 51778` never match each
    # other, and `Vma ms 1067 (1)` is not the parent of `VMA MS-1067 (1-6)`.
    th, rh = tokens(shelfmark)
    parent = sorted({f for (sg, _), fs in shelf.items() if sg == siglum for f in fs
                     for tf, rf in [tokens(where[f][1])]
                     if tf and not rf and not rh and len(tf) >= 2
                     and len(tf) < len(th) and th[:len(tf)] == tf})
    return parent, ('parent volume' if parent else None)


def build():
    sp, (shelf, by_rism, claims, own, where) = spine(), held()
    by_edition = editions()
    state = folder_state()
    rows = []
    for p in sorted(CACHE.glob('*.xml')):
        sid = p.stem
        try:
            rec = rd.marc(sid, CACHE); m = rd.describe(sid, rec)
        except Exception:
            continue
        gs = sorted({*(m['gerard_numbers'] or []), *([m['gerard']] if m['gerard'] else [])},
                    key=rd.gnum)
        opus = sorted({sp[g][0] for g in gs if g in sp})
        holds = []
        hs = [h for h in m['holdings'].values() if h.get('siglum')]
        on = placed(sid, hs, by_rism, own, where)
        for i, h in enumerate(hs):
            folders, how = held_for(sid, h['siglum'], h.get('shelfmark'),
                                    shelf, claims, where, sorted(on.get(i, [])))
            holds.append(dict(siglum=h['siglum'], shelfmark=h.get('shelfmark'),
                              former=h.get('former_shelfmark'),
                              institution=h.get('institution'), held=folders, how=how))
        rows.append(dict(
            rism=sid, url=f'https://rism.online/sources/{sid}',
            gerard=gs, opus=opus,
            # (opus, number) pairs, not prose: this is a join key, not a label
            opus_no=[[sp[g][0], sp[g][1]] for g in gs
                     if g in sp and sp[g][0] is not None and sp[g][1] is not None],
            title=m['full_title'] or m['title'], type='/'.join(m['source_types']),
            autograph=m['is_autograph'],
            publisher=(m['published'] or {}).get('publisher'),
            place=(m['published'] or {}).get('place'),
            date=(m['published'] or {}).get('date'),
            plates=m['plate_numbers'], incipits=m['incipits'],
            holdings=holds,
            held=sorted({f for h in holds for f in h['held']}),
            held_how=next((h['how'] for h in holds if h['held']), None),
            # what stands behind the label on each copy we hold
            held_state={f: state.get(f, ('F', evidence.LABEL['F']))[0]
                        for h in holds for f in h['held']},
            # the same edition on disk, from a copy RISM does not catalogue
            held_edition=sorted(by_edition.get(sid, set())),
            # some copy of this source, not necessarily the one cited
            held_any=sorted(by_rism.get(sid, set()) | {f for h in holds for f in h['held']})))
    return rows


def lib_index(rows):
    """Institution name -> siglum, for citations that spell the library out."""
    out = {}
    for r in rows:
        for h in r['holdings']:
            if h.get('institution') and len(h['institution']) > 12:
                out.setdefault(h['institution'].lower(), h['siglum'])
    return out


def shelf_index(rows):
    """Normalised shelfmark -> {siglum}, for citations that give no siglum."""
    out = collections.defaultdict(set)
    for r in rows:
        for h in r['holdings']:
            for k in (h.get('shelfmark'), h.get('former')):
                n = norm(k)
                if len(n) >= 5: out[n].add(h['siglum'])
    return out


def signals(text):
    """Every handle a citation might carry. Shelfmarks are whatever follows a siglum."""
    s = dict(rism=set(RISMID.findall(text)), gerard=set(GERARD.findall(text)),
             ppn=set(PPN.findall(text)), ark=set(ARK.findall(text)),
             opus_no=set(), opus=set(), pairs=set())
    for o, n in OPUSNO.findall(text): s['opus_no'].add((int(o), int(n)))
    s['opus'] = {int(o) for o in OPUS.findall(text)} - {o for o, _ in s['opus_no']}
    for m in SIGLUM.finditer(text):
        tail = text[m.end():m.end() + 40]
        tail = re.split(r'[;,]|\s{2,}|\band\b|\bin\b', tail)[0].strip(' .:')
        if norm(tail): s['pairs'].add((m.group(1), norm(tail)))
    return s


def enrich(sig, text, libs, shelves):
    """Recover a siglum the citation spelled out, and a shelfmark it gave bare."""
    low, flattened = text.lower(), flat(text)
    named = {sg for name, sg in libs.items() if name in low}
    for n, sgs in shelves.items():
        if n in flattened:
            for sg in (named & sgs) or sgs:
                sig['pairs'].add((sg, n))
    for sg in named:
        if not any(p[0] == sg for p in sig['pairs']): sig['pairs'].add((sg, ''))
    return sig


def match(text, rows, limit=5, libs=None, shelves=None):
    sig = signals(text)
    if libs is not None: sig = enrich(sig, text, libs, shelves)
    scored = []
    for r in rows:
        sc, why = 0, []
        if r['rism'] in sig['rism']: sc += 120; why.append('RISM id')
        for h in r['holdings']:
            for cited_sig, cited_shelf in sig['pairs']:
                if h['siglum'] != cited_sig: continue
                if not cited_shelf: sc += 8; why.append(f'{cited_sig} (library only)'); continue
                for cand in (h['shelfmark'], h['former']):
                    n = norm(cand)
                    if not n: continue
                    if n == cited_shelf or n.startswith(cited_shelf) or cited_shelf.startswith(n):
                        sc += 100; why.append(f"{h['siglum']} {h['shelfmark']}")
                        break
                else:
                    sc += 8; why.append(f'{cited_sig} (library only)')
        if sig['gerard'] & set(r['gerard']): sc += 20; why.append('Gérard')
        if sig['opus_no'] & {(o, n) for o, n in r['opus_no']}:
            sc += 25; why.append('opus + no.')
        elif sig['opus'] & set(r['opus']): sc += 6; why.append('opus')
        blob = json.dumps(r)
        if any(x in blob for x in sig['ppn']): sc += 60; why.append('PPN')
        if any(x in blob for x in sig['ark']): sc += 60; why.append('ark')
        if sc: scored.append((sc, sorted(set(why)), r))
    scored.sort(key=lambda x: (-x[0], x[2]['rism']))
    return scored[:limit]


def report(text, rows, out=sys.stdout, libs=None, shelves=None):
    hits = match(text, rows, libs=libs, shelves=shelves)
    print(f'\n{text.strip()[:96]}', file=out)
    if not hits:
        print('   no candidate', file=out); return
    for sc, why, r in hits:
        g = ', '.join(r['gerard']) or '—'
        how = r.get('held_how')
        if r['held']:
            tiers = ''.join(sorted({r.get('held_state', {}).get(f, '?')
                                    for f in r['held'][:2]}))
            mark = ('  ✓ HELD ' + ', '.join(r['held'][:2])
                    + (f' [{how}]' if how and how != 'copy' else '')
                    + (f'  ({tiers})' if tiers else ''))
        elif r.get('held_edition'):
            mark = '  ≈ same edition held: ' + ', '.join(r['held_edition'][:2])
        elif r['held_any']:
            mark = '  ~ other copy held'
        else:
            mark = '  — not held'
        print(f"   [{sc:>3}] G {g:<18} {r['rism']:<10} {r['type'][:16]:16}{mark}", file=out)
        print(f"         {' · '.join(why)}", file=out)
        print(f"         {(r['title'] or '')[:88]}", file=out)


def tables(rows):
    Path('concordance.jsonl').write_text(
        ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    by_lib = collections.defaultdict(list)
    for r in rows:
        for h in r['holdings']:
            by_lib[h['siglum']].append((h, r))
    L = ['# Concordance — citation to RISM source to what we hold', '',
         f'{len(rows)} RISM sources, {sum(len(r["holdings"]) for r in rows)} holdings, '
         f'{len({f for r in rows for f in r["held"]})} folders on disk.', '',
         'Indexed by **library and shelfmark**, because that is how sources get cited. The '
         'machine-readable form is `../concordance.jsonl`, one row per RISM source carrying '
         'every handle it has: RISM id, Gérard numbers, opus and number, publisher, plate '
         'number, every holding, and the folders holding a scan.', '',
         'To resolve a citation:', '', '```sh',
         'uv run boc.py find "F-Po RES-507 (14)"',
         'uv run tools/concordance.py --match-file my-notes.md', '```', '',
         'Three strengths of answer, kept apart because they mean different things:', '',
         '- `✓ folder` — we hold **that copy**: the folder says it is a copy of that source.',
         '- `✓ folder (parent volume)` — we hold the **volume containing it**. RISM '
         'catalogues the six quartets inside D-B `KHM 577` as `KHM 577 (1)` … `(6)`; the '
         'scan is of the whole volume.',
         '- `≈ folder (edition)` — we hold **another library\'s copy of the same edition**. '
         'RISM does not catalogue ours at that shelfmark, usually because it records the '
         'edition with `[no indication]` where a shelfmark should be.', '',
         '`AUT` means RISM calls it an autograph. The letter after a held folder is what '
         'stands behind its label — **A** checked by eye, **B** established from the scan, '
         '**C** RISM states it for this copy, **D** asserted and never checked, **E** the '
         'pages disagree, **F** nothing. See `STATE-OF-EVIDENCE.md`.', '',
         '> **A shelfmark is not always one object.** D-B `DMS 51778` covers many Berlin '
         'editions, E-Mn `M/680-683` holds two Bremner sets bound together, and F-Pn '
         '`VMB MS-153` is five items. Where a shelfmark is shared, a `✓` says that shelfmark '
         'is represented on disk — not that the exact item cited is the file you will open.',
         '', '---', '']
    for sig in sorted(by_lib):
        rs = by_lib[sig]
        inst = next((h['institution'] for h, _ in rs if h.get('institution')), '')
        got = sum(1 for h, _ in rs if h['held'])
        L += ['', f'## {sig} — {inst} ({len(rs)}'
              + (f', {got} held' if got else '') + ')', '',
              '| shelfmark | G | opus | type | RISM | held |', '|---|---|---|---|---|---|']
        for h, r in sorted(rs, key=lambda x: (norm(x[0]['shelfmark']), x[1]['rism'])):
            L.append('| {} | {} | {} | {} | [{}]({}) | {} |'.format(
                rd.cell(h['shelfmark'] or '—'), rd.cell(', '.join(r['gerard']) or '—'),
                rd.cell(', '.join(f'op. {o}' for o in r['opus']) or '—'),
                rd.cell((r['type'] or '') + (' **AUT**' if r['autograph'] else '')),
                r['rism'], r['url'],
                ('✓ `' + h['held'][0] + '` '
                 + r.get('held_state', {}).get(h['held'][0], '?')
                 + (f" *({h['how']})*" if h.get('how') and h['how'] != 'copy' else ''))
                if h['held'] else
                ('≈ `' + r['held_edition'][0] + '` *(edition)*' if r.get('held_edition') else '—')))
    # Everything on disk that no RISM holding above accounts for. Without this the table
    # answers "is this citation in RISM" rather than "do we have it", and the Library of
    # Congress scans, the BNE downloads and most of the BnF prints would fall through.
    seen = {f for r in rows for h in r['holdings'] for f in h['held']}
    orphans = []
    for q in sorted(DIG.rglob('metadata.json')):
        d = q.parent
        if not any(f.suffix.lower() in MEDIA for f in d.iterdir() if f.is_file()): continue
        rel = str(d.relative_to(DIG))
        if rel in seen: continue
        try:
            m = json.loads(q.read_text())
        except Exception:
            continue
        orphans.append((rel, m))
    if orphans:
        L += ['', '---', '', '## On disk, but not matched to a RISM holding',
              '', f'{len(orphans)} folders. Either RISM does not catalogue the source at all '
              '(the Library of Congress manuscripts, most of the BnF prints), or it catalogues '
              'the edition without recording this library\'s shelfmark. Cite them by folder.', '',
              '| folder | siglum | shelfmark | G | what it is | RISM (work) |',
              '|---|---|---|---|---|---|']
        for rel, m in orphans:
            us = walk_urls(m.get('rism_related')) or walk_urls(m.get('source'))
            rr = us[0] if us else None
            L.append('| `{}` | {} | {} | {} | {} | {} |'.format(
                rel, rd.cell(m.get('siglum') or '—'), rd.cell(m.get('shelfmark') or '—'),
                rd.cell(m.get('gerard_label') or m.get('gerard') or '—'),
                rd.cell((m.get('title') or '')[:44]),
                (f'[{rr.rstrip("/").rsplit("/", 1)[-1]}]({rr})'
                 + (' *(work)*' if m.get('rism_relation') == 'work' else '')) if rr else '—'))
        L.append('')

    (DIG / 'CONCORDANCE.md').write_text('\n'.join(L))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--match', help='resolve one citation')
    ap.add_argument('--match-file', help='resolve every citation-looking line in a file')
    a = ap.parse_args()
    rows = build()
    if a.match:
        report(a.match, rows, libs=lib_index(rows), shelves=shelf_index(rows))
    elif a.match_file:
        text = Path(a.match_file).read_text(errors='replace')
        lines = [l for l in text.splitlines()
                 if l.strip() and (SIGLUM.search(l) or RISMID.search(l) or GERARD.search(l))]
        print(f'{len(lines)} citation-looking lines in {a.match_file}', file=sys.stderr)
        libs, shelves = lib_index(rows), shelf_index(rows)
        for l in lines: report(l, rows, libs=libs, shelves=shelves)
    else:
        tables(rows)
        print(f'{len(rows)} sources -> concordance.jsonl, {DIG}/CONCORDANCE.md', file=sys.stderr)
