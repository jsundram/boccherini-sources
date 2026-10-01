# /// script
# requires-python = ">=3.11"
# ///
"""Fill the gaps in the sidecars from what RISM already says, in one place.

    uv run tools/normalize_metadata.py --dry-run
    uv run tools/normalize_metadata.py

Three fields were inconsistent across `digitizations/*/metadata.json`, and every consumer
was compensating differently:

**publisher** — RISM fills `260 $b` for only a handful of records. For most prints the
imprint is instead the last bracketed phrase of the title: *"... opera prima [Amsterdam,
J. J. Hummel]"*. Same fact, different field, so it is copied into `publisher` and
`publication_place` with `publisher_established_by` recording where it came from.

**rism_related** — grew three shapes: a string, a list, and a dict keyed by Gérard number.
Normalised to a list of URLs. The old value is kept as `rism_related_raw` the first time.

**work-level links** — 34 items came from library portals, not from RISM, and RISM does not
catalogue them at those shelfmarks. It does catalogue the same editions elsewhere, so each
gets the sources that share its Gérard numbers, marked `rism_relation: "work"` so nobody
mistakes it for a link to this copy.

Nothing is invented: every value written is traceable to a RISM record or to a title page,
and the field that says so is written alongside it.
"""
import argparse, importlib.util, json, re, sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('rd', 'tools/rism_digitizations.py')
rd = importlib.util.module_from_spec(spec); spec.loader.exec_module(rd)
CACHE = Path('.rism-cache'); rd.cache_dir[0] = CACHE
DIG = Path('digitizations')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')
# A trailing bracketed imprint: "... opera prima [Amsterdam, J. J. Hummel]"
IMPRINT = re.compile(r'\[([^\]]{4,220}?)\]\s*$')


def urls(v, out):
    if isinstance(v, str):
        if '/sources/' in v: out.append(v)
    elif isinstance(v, list):
        for x in v: urls(x, out)
    elif isinstance(v, dict):
        for x in v.values(): urls(x, out)
    return out


def imprint_of(title):
    """(place, publisher) from a trailing bracketed imprint, or None.

    Requires a comma: '[Amsterdam, J. J. Hummel]' is an imprint, '[1785]' is a date and
    '[without title]' is a cataloguer's note. Gallica ends many titles with a bracketed
    catalogue reference -- '[Y. Gerard, 171-176]' -- which has a comma and letters and is
    emphatically not a publisher, so anything naming Gerard is rejected outright and the
    publisher half must actually read as a name."""
    m = IMPRINT.search((title or '').strip())
    if not m: return None
    s = m.group(1).strip()
    if not re.search(r'[,:]', s) or not any(c.isalpha() for c in s): return None
    if re.search(r'g[ée]rard|gerb|\brism\b', s, re.I): return None
    # A print can name several cities: '[Paris, La Chevardière; Lyon, Castaud; ...]'.
    # The first is the primary imprint; the rest are agents.
    first = s.split(';')[0].strip()
    parts = re.split(r'[,:]', first, maxsplit=1)
    if len(parts) != 2: return None
    place, pub = (x.strip() for x in parts)
    if len(re.findall(r'[A-Za-zÀ-ÿ]', pub)) < 3: return None
    # A cataloguer's note ('[title page, vl 1:]') or a key list ('[c, B|b, D, ...]') never
    # opens with a capitalised place name.
    if not re.match(r'^[A-ZÀ-Ý][a-zà-ÿ]', place): return None
    more = len([x for x in s.split(';') if x.strip()]) - 1
    return place, pub + (f' (and {more} other imprint{"s" if more > 1 else ""})' if more else '')


STOP = set('the of for and per due e a il la di del con les des pour deux sei six vi und'.split())


def words(t):
    return {w for w in re.findall(r'[a-zà-ÿ0-9]{3,}', (t or '').lower()) if w not in STOP}


def title_index():
    """RISM sources by title words, for matching an edition RISM numbers differently.

    The exact-Gérard join cannot reach Pleyel's 'Douze quatuors, oeuvre 39': RISM gives the
    whole twelve-quartet anthology a single number, G 234, while our folders carry the
    livraison's own numbers, established by hand from the scans. The titles, though, are
    nearly the same sentence."""
    import math
    rows = []
    for p in sorted(CACHE.glob('*.xml')):
        try:
            m = rd.describe(p.stem, rd.marc(p.stem, CACHE))
        except Exception:
            continue
        t = m['full_title'] or m['title']
        w = words(t)
        if len(w) >= 4:
            rows.append((p.stem, w, t))
    df = {}
    for _, w, _ in rows:
        for x in w: df[x] = df.get(x, 0) + 1
    idf = {k: math.log(len(rows) / (1 + v)) for k, v in df.items()}
    return rows, idf


def best_by_title(title, rows, idf, floor=9.0):
    """RISM sources whose title matches this one strongly. Empty when nothing is close.

    A shared opus or oeuvre number is required as well as the words. Boccherini's title
    pages are formulaic -- 'Tre quartetti per due Violini, Viola e Basso' fits a dozen
    unrelated sources -- and on words alone the Library of Congress Op. 54 matched a
    Naples manuscript of G 165. The number is what makes 'oeuvre 39' mean oeuvre 39."""
    w = words(title)
    if len(w) < 4: return []
    # Read the numbers off the raw title: words() drops anything under three characters,
    # so '39' -- the whole point of 'oeuvre 39' -- never reached this test.
    nums = set(re.findall(r'\d{2,}', title or ''))
    scored = []
    for sid, rw, rt in rows:
        shared = w & rw
        if len(shared) < 4: continue
        if nums and not (nums & set(re.findall(r'\d{2,}', rt or ''))): continue
        s = sum(idf.get(x, 0) for x in shared)
        if s >= floor: scored.append((s, sid))
    scored.sort(reverse=True)
    top = scored[0][0] if scored else 0
    return [sid for s, sid in scored if s >= top * 0.92][:6]


def rism_index():
    """Gérard-number signature -> RISM sources, for the work-level join."""
    idx = {}
    for p in sorted(CACHE.glob('*.xml')):
        try:
            m = rd.describe(p.stem, rd.marc(p.stem, CACHE))
        except Exception:
            continue
        g = tuple(sorted({*(m['gerard_numbers'] or []),
                          *([m['gerard']] if m['gerard'] else [])}, key=rd.gnum))
        if not g: continue
        kind = 'print' if ('Print' in (m['source_types'] or [])
                           or m['record_type'] == 'print') else 'manuscript'
        idx.setdefault((g, kind), []).append(p.stem)
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    idx = rism_index()
    trows, idf = title_index()
    changed = 0
    for f in sorted(DIG.rglob('metadata.json')):
        d = f.parent
        if not any(x.suffix.lower() in MEDIA for x in d.iterdir() if x.is_file()):
            continue
        m = json.loads(f.read_text())
        before = json.dumps(m, sort_keys=True)
        notes = []

        # 1. one shape for rism_related
        got = urls(m.get('source'), []) + urls(m.get('rism_related'), []) \
            + urls(m.get('rism_constituents'), [])
        seen, uniq = set(), []
        for u in got:
            if u not in seen: seen.add(u); uniq.append(u)
        if uniq:
            if not isinstance(m.get('rism_related'), list) and m.get('rism_related') is not None:
                m.setdefault('rism_related_raw', m['rism_related'])
            m['rism_related'] = uniq
            m.setdefault('rism_relation', 'copy')

        # 2. publisher from the title imprint, when RISM's 260 is empty
        pub = (m.get('published') or {}).get('publisher') or m.get('publisher')
        if not pub:
            im = imprint_of(m.get('full_title') or m.get('title'))
            if im:
                place, publisher = im
                m['publisher'] = publisher
                m.setdefault('publication_place', place)
                m['publisher_established_by'] = (
                    'Imprint at the end of the RISM title; RISM leaves 260 $b empty.')
                notes.append(f'publisher={publisher}')

        # 3. work-level links for items RISM does not catalogue at this shelfmark
        # A source that is not a quartet has no business being matched to one.
        if not uniq and m.get('form') != 'not-a-quartet':
            g = tuple(sorted({*(m.get('gerard_numbers') or []),
                              *([m['gerard']] if m.get('gerard') else [])}, key=rd.gnum))
            kind = 'print' if (m.get('medium') == 'print'
                               or m.get('record_type') == 'print'
                               or 'Print' in (m.get('source_types') or [])) else 'manuscript'
            cands = idx.get((g, kind)) or idx.get((g, 'print')) or idx.get((g, 'manuscript')) or []
            how = 'matched on the Gérard set'
            if not cands:
                cands = best_by_title(m.get('full_title') or m.get('title'), trows, idf)
                how = ('matched on the title; the Gérard numbers differ because RISM numbers '
                       'this edition as a whole while this folder carries the livraison\'s own')
            if cands:
                m['rism_related'] = [f'https://rism.online/sources/{s}' for s in sorted(cands)[:6]]
                m['rism_relation'] = 'work'
                m['rism_related_established_by'] = (
                    f"This copy is not in RISM -- it was found on a library portal. These are "
                    f"RISM's records for the same {kind} of the same works (GerB "
                    f"{', '.join(g) or '?'}), {how}. They describe the edition, not this copy.")
                notes.append(f'work link -> {len(cands)} source(s)')

        if json.dumps(m, sort_keys=True) != before:
            changed += 1
            print(f"  {str(d.relative_to(DIG)):38} {'; '.join(notes) or 'shape'}", file=sys.stderr)
            if not a.dry_run:
                f.write_text(json.dumps(m, indent=1, ensure_ascii=False) + '\n')
    print(f"{changed} sidecars {'would change' if a.dry_run else 'updated'}", file=sys.stderr)


if __name__ == '__main__':
    main()
