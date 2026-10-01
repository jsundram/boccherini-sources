# /// script
# requires-python = ">=3.11"
# ///
"""Validate a folder against the intake spec before it becomes part of the archive.

Required means *every* item in the archive already carries it and a consumer breaks without
it -- only `siglum`, `title` and `source` clear that bar. Everything else is checked for
shape and for the consequence of leaving it out, and reported as a warning naming what
degrades. An earlier draft of this file marked eight fields required and failed all 143
existing items, which would have made it useless as a gate.

An upstream pipeline can run this on what it produced and get a verdict without touching
this repository's data. It checks the things the archive's consumers actually require --
`concordance.py` for search, `check_archive.py` for the invariants, `build_sources_page.py`
for display, `evidence.py` for the tier -- so a folder that passes here drops in without a
rebuild failing afterwards.

    uv run tools/check_intake.py <folder> [<folder> ...]
    uv run tools/check_intake.py --all            # every item already in digitizations/
    uv run tools/check_intake.py --spec           # print the spec as JSON

`digitizations/INTAKE-SPEC.md` is the prose version. This file is the authority: if the two
disagree, the document is wrong.
"""
import argparse, json, sys
from pathlib import Path

DIG = Path('digitizations')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')

# field -> (required?, type, why it matters)
SPEC = {
 'siglum':         (True,  str,  'RISM library siglum, e.g. "F-Pn". Half of the search key; '
                                 'a holding with no siglum is skipped by the concordance.'),
 'shelfmark':      (False,  str,  'As the library writes it, e.g. "Vma ms 1067 (1)". The other '
                                 'half of the search key. MUST CONTAIN A DIGIT: `norm()` in '
                                 'concordance.py returns "" otherwise and the item becomes '
                                 'unfindable by shelfmark.'),
 'institution':    (False,  str,  'Full library name; lets a citation that spells the library '
                                 'out resolve to the siglum.'),
 'title':          (True,  str,  'What the source calls itself. Shown everywhere.'),
 'gerard':         (False,  str,  'Primary Gerard number AS A STRING. An int breaks gnum().'),
 'gerard_numbers': (False,  list, 'Every Gerard number in this item, strings. One entry is '
                                 'normal; a volume holding several lists them all.'),
 'gerard_label':   (False,  str,  'How the folder is named: "228", or "245-247" for a range.'),
 'rism_relation':  (False,  str,  '"copy" when this is a copy of that RISM source -- the only '
                                 'value the concordance treats as a claim to hold it. "work" '
                                 'means the record is for the same music elsewhere, and is '
                                 'deliberately NOT a holding claim.'),
 'source':         (True,  str,  'Where it came from: a portal name, a RISM URL, or '
                                 '"private-photography" for a scan made in person.'),
 'pages':          (False,  int,  'Page count of the PDF.'),
 'files':          (False,  dict, 'What is in the folder, e.g. {"all": "<folder>.pdf"}.'),
 'source_id':      (False, str,  'RISM source id for THIS copy, if RISM catalogues it. With '
                                 'this the concordance can answer definitively rather than '
                                 'guessing from the shelfmark. Strongly wanted.'),
 'rism_related':   (False, list, 'RISM URLs. With rism_relation "copy" these are read as '
                                 'claims to hold those sources.'),
 'medium':         (False, str,  'print | manuscript | autograph.'),
 'form':           (False, str,  'quartet | not-a-quartet. If not-a-quartet, also set '
                                 'not_quartet_reason or `boc check` fails.'),
 'parts':          (False, (list, dict), 'Part NAMES, not a count: ["violin1","violin2","viola",'
                                 '"cello"]. An int here crashes build_sources_page.py.'),
 'arrived_as':     (False, str,  'Set to "pdf" when the item was supplied as a finished PDF. '
                                 'Without it, `check_archive` demands a page_index recording '
                                 'what the page-image filenames meant.'),
 'opus':           (False, str,  'e.g. "Op. 48".'),
 'key':            (False, str,  'e.g. "B minor".'),
 'year':           (False, str,  'Composition year.'),
 'date_statement': (False, str,  'Free text: what the source says about its own date.'),
 'former_shelfmark': (False, str, 'Also indexed for search, so old citations resolve.'),
 'url':            (False, str,  'A re-fetchable address. An item with NO url/manifest/ark/'
                                 'mets must be declared with `boc protect`, or `boc check` '
                                 'fails: every item needs either a way back or a checksum.'),
}
PROVENANCE = ('gerard_established_by', 'established_by', 'corrected')

# what leaving a recommended field out actually costs, rather than a blanket "missing"
NAMED = {
 'shelfmark':   'the item cannot be found by shelfmark, only by RISM id',
 'gerard_label': 'the folder cannot be filed under G<label>, and the shelf page has no '
                 'heading for it',
 'gerard':      'the item counts as unidentified in `boc status` and `boc check` fails '
                'unless form is "not-a-quartet"',
 'rism_relation': 'the concordance will not treat this as holding any RISM source',
 'institution': 'a citation spelling the library out will not resolve to the siglum',
}


def tname(t):
    return t.__name__ if isinstance(t, type) else ' or '.join(x.__name__ for x in t)


def declared(d):
    """Is this folder already declared irreplaceable? An item with no way back is fine
    exactly when a checksum stands in for one."""
    f = Path('originals.jsonl')
    if not f.exists():
        return False
    try:
        rel = str(d.resolve().relative_to(DIG.resolve()))
    except ValueError:
        rel = d.name
    names = set()
    for line in f.read_text().splitlines():
        if line.strip():
            names.add(json.loads(line)['folder'])
    return rel in names or any(n.endswith('/' + d.name) for n in names)


def check(d):
    """[(level, message)] -- 'error' blocks intake, 'warn' degrades something."""
    out = []
    err = lambda s: out.append(('error', s))
    warn = lambda s: out.append(('warn', s))

    if not d.is_dir():
        return [('error', f'{d}: not a directory')]

    mf = d / 'metadata.json'
    if not mf.exists():
        return [('error', 'no metadata.json')]
    try:
        m = json.loads(mf.read_text())
    except Exception as e:
        return [('error', f'metadata.json is not valid JSON: {e}')]

    media = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in MEDIA]
    if not media and m.get('skipped'):
        # A recorded decision not to download is as settled as holding the thing, and
        # `parse_portal_results.py` reads it off the folder to keep the item off the
        # worklist. Reporting the absent scan as an error told you to delete the decision.
        warn(f'no scan, deliberately: {m.get("skip_reason") or "skipped, no reason given"}')
    elif not media:
        err('no media file; the concordance and the shelf both skip a folder with none')
    if m.get('skipped') and not m.get('skip_reason'):
        err('skipped with no skip_reason: a decision with no account of itself')
    pdf = d / f'{d.name}.pdf'
    imgs = [f for f in media if f.suffix.lower() != '.pdf']
    if imgs and not pdf.exists():
        err(f'page images with no collated PDF; it must be named {d.name}.pdf')

    for k, (req, typ, _why) in SPEC.items():
        if k not in m or m[k] in (None, '', [], {}):
            if req:
                err(f'missing required field: {k}')
            elif k in NAMED:
                warn(f'no {k}: {NAMED[k]}')
            continue
        if not isinstance(m[k], typ):
            err(f'{k}: expected {tname(typ)}, got {type(m[k]).__name__} ({m[k]!r})')

    # the things that have actually gone wrong here
    if isinstance(m.get('gerard'), str) and not m['gerard'].isdigit():
        warn(f'gerard is not a bare number: {m["gerard"]!r}')
    if isinstance(m.get('gerard_numbers'), list) and any(
            not isinstance(g, str) for g in m['gerard_numbers']):
        err('gerard_numbers must be strings; ints break gnum()')
    if isinstance(m.get('parts'), list) and any(not isinstance(p, str) for p in m['parts']):
        err('parts must be part NAMES, not a count')
    sm = m.get('shelfmark')
    if isinstance(sm, str) and not any(c.isdigit() for c in sm):
        # '[no indication]' is RISM's own placeholder for a holding it records without a
        # shelfmark -- 24 items here carry it faithfully. That is upstream's fact, not an
        # intake mistake. A digit-free shelfmark that is NOT the placeholder is a mistake.
        if sm.strip().lower() == '[no indication]':
            warn('shelfmark is RISM\'s "[no indication]" placeholder, so this is findable '
                 'by RISM id only, never by shelfmark')
        else:
            err(f'shelfmark {sm!r} has no digit, so concordance.norm() discards it and the '
                'item cannot be found by shelfmark')
    if m.get('rism_relation') not in ('copy', 'work', None):
        err(f'rism_relation must be "copy" or "work", not {m["rism_relation"]!r}')
    if m.get('rism_relation') == 'work':
        warn('rism_relation "work" is not a claim to hold the source; use "copy" if this IS '
             'a copy of it, or the concordance will report the record as not held')
    if not (m.get('source_id') or m.get('rism_related')):
        warn('no source_id and no rism_related: nothing ties this to RISM, and `boc check` '
             'requires every item to be reachable from a RISM record')
    if (m.get('gerard') or m.get('gerard_numbers')) and not (
            any(m.get(k) for k in PROVENANCE) or m.get('rism_relation') == 'copy'):
        err('a Gerard label with no provenance: set one of '
            f'{", ".join(PROVENANCE)}, or rism_relation "copy"')
    if m.get('form') == 'not-a-quartet' and not m.get('not_quartet_reason'):
        err('form "not-a-quartet" requires not_quartet_reason')
    if pdf.exists() and not imgs and m.get('arrived_as') != 'pdf' and not m.get('page_index'):
        warn('supplied as a PDF but arrived_as is not "pdf"; `check_archive` will ask for a '
             'page_index that does not apply')
    refetch = any(m.get(k) for k in ('url', 'manifest', 'ark', 'mets', 'bne_digital_url'))
    if not refetch and not declared(d):
        warn('no re-fetchable address and not declared irreplaceable: run '
             '`uv run boc.py protect --declare <folder> --from "..."`, or `boc check` fails')

    # folder naming: <source_id>_<siglum> is what the archive uses
    if m.get('source_id') and m.get('siglum'):
        want = f'{m["source_id"]}_{m["siglum"]}'
        if d.name != want:
            warn(f'folder is {d.name!r}; the convention is {want!r} '
                 '(<source_id>_<siglum>)')
    if m.get('gerard_label') and d.parent.name != f'G{m["gerard_label"]}':
        warn(f'parent folder is {d.parent.name!r}; the convention is '
             f'"G{m["gerard_label"]}"')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('dirs', nargs='*')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--spec', action='store_true')
    a = ap.parse_args()

    if a.spec:
        print(json.dumps({k: dict(required=r, type=tname(t), why=w)
                          for k, (r, t, w) in SPEC.items()}, indent=1))
        return

    dirs = [Path(x) for x in a.dirs]
    if a.all:
        dirs = sorted(p.parent for p in DIG.rglob('metadata.json'))
    if not dirs:
        sys.exit('nothing to check: give a folder, or --all')

    errs = warns = 0
    for d in dirs:
        res = check(d)
        e = [x for x in res if x[0] == 'error']
        w = [x for x in res if x[0] == 'warn']
        errs += len(e); warns += len(w)
        if res:
            print(f'\n{d}')
            for lvl, msg in res:
                print(f'  {"ERROR" if lvl == "error" else "warn ":6} {msg}')
    print(f'\n{len(dirs)} folder(s): {errs} error(s), {warns} warning(s)')
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()
