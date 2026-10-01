# /// script
# requires-python = ">=3.11"
# ///
"""Propose Gerard numbers for the folders that still have none.

Nothing here decides anything. It gathers the evidence a person would look at anyway and
puts it in one file, ranked, so the judgement is quick instead of slow. Three independent
signals, because no one of them is reliable on its own:

  shelfmark  RISM indexes holdings by siglum + shelfmark, so a folder whose shelfmark RISM
             also records inherits that record's GerB number. Exact, when it fires -- but it
             rarely does for the BnF prints, which RISM catalogues by edition with
             '[no indication]' where a shelfmark should be.

  title      RISM's own titles are quoted from the same title pages our scans show, so
             distinctive wording matches. Scored on rare-word overlap: 'quartetti' is in
             every title and tells you nothing, 'concertanti' or 'dilettanti' narrows it.

  libro      Boccherini's publishers numbered the quartet sets as 'libro primo' through
             'libro settimo'. Where a title says which book it is, any RISM record using the
             same phrase and carrying a GerB number is a candidate.

Run: uv run tools/suggest_ids.py  ->  digitizations/TO-IDENTIFY.md
"""
import importlib.util, json, math, pathlib, re, collections

spec = importlib.util.spec_from_file_location('rd', 'tools/rism_digitizations.py')
rd = importlib.util.module_from_spec(spec); spec.loader.exec_module(rd)
CACHE = pathlib.Path('.rism-cache'); rd.cache_dir[0] = CACHE
OUT = pathlib.Path('digitizations')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')
LIBRO = re.compile(r'libro\s+(primo|secondo|terzo|quarto|quinto|sesto|settimo|\d+)', re.I)
STOP = set('the of for and per due e a il la di del con les des pour deux sei six vi'.split())


def words(t):
    return [w for w in re.findall(r'[a-zà-ÿ]{3,}', (t or '').lower()) if w not in STOP]


def rism_records():
    recs = []
    for p in sorted(CACHE.glob('*.xml')):
        try:
            m = rd.describe(p.stem, rd.marc(p.stem, CACHE))
        except Exception:
            continue
        g = sorted({*(m['gerard_numbers'] or []), *([m['gerard']] if m['gerard'] else [])},
                   key=rd.gnum)
        if not g: continue
        t = ' '.join(filter(None, (m['full_title'], m['title'])))
        recs.append(dict(sid=p.stem, g=g, title=t, words=set(words(t)),
                         libro=(LIBRO.search(t).group(1).lower() if LIBRO.search(t) else None),
                         holds={(h.get('siglum'), rd.norm_shelf(h.get('shelfmark')))
                                for h in m['holdings'].values()}))
    return recs


def main():
    recs = rism_records()
    # inverse document frequency, so a shared rare word counts and a shared common one does not
    df = collections.Counter(w for r in recs for w in r['words'])
    idf = {w: math.log(len(recs) / (1 + n)) for w, n in df.items()}

    todo = []
    for p in sorted(OUT.rglob('metadata.json')):
        d = p.parent
        if not [f for f in d.iterdir() if f.suffix.lower() in MEDIA]: continue
        m = json.loads(p.read_text())
        if m.get('gerard') or m.get('gerard_numbers'): continue
        if m.get('form') == 'not-a-quartet': continue   # settled, just not a quartet
        todo.append((d, m))

    if not todo:
        (OUT / 'TO-IDENTIFY.md').write_text(
            '# Still to identify\n\n**Nothing.** Every folder holding images carries a Gérard '
            'number, or is marked `form: not-a-quartet` with the reason.\n\n'
            'Re-run `uv run tools/suggest_ids.py` after adding material and this file will fill '
            'again.\n')
        print(f'0 unidentified -> {OUT}/TO-IDENTIFY.md')
        return

    L = ['# Still to identify', '',
         f'{len(todo)} folders hold images but carry no Gérard number. Each one below lists what '
         'the evidence suggests; none of it has been accepted.', '',
         'Signals are independent: **shelfmark** is exact when RISM records the same shelfmark, '
         '**title** is rare-word overlap against RISM titles quoted from the same title pages, '
         '**libro** is the publisher\'s book number where the title states it.', '']

    for d, m in todo:
        key = (m.get('siglum'), rd.norm_shelf(m.get('shelfmark')))
        title = m.get('title') or ''
        tw = set(words(title))
        lib = LIBRO.search(title)
        lib = lib.group(1).lower() if lib else None

        scored = []
        for r in recs:
            s = sum(idf.get(w, 0) for w in tw & r['words'])
            why = []
            if key[0] and key[1] and key in r['holds']:
                s += 100; why.append('**shelfmark**')
            if lib and r['libro'] == lib: s += 8; why.append(f'libro {lib}')
            if s > 3: scored.append((s, r, why))
        scored.sort(key=lambda x: -x[0])

        n = len([f for f in d.iterdir() if f.suffix.lower() in MEDIA])
        L += [f"## `{d.relative_to(OUT)}`", '',
              f"{m.get('siglum') or '—'} · {m.get('shelfmark') or 'no shelfmark'} · {n} files"
              + (f" · [Gallica]({m['ark']})" if m.get('ark') else ''), '',
              f"> {title[:150]}", '']
        if not scored:
            L += ['No candidate.', '']
            continue
        L += ['| score | G | RISM | why | RISM title |', '|---:|---|---|---|---|']
        for s, r, why in scored[:4]:
            L.append(f"| {s:.0f} | **{', '.join(r['g'])}** | "
                     f"[{r['sid']}](https://rism.online/sources/{r['sid']}) "
                     f"| {' '.join(why) or 'title'} | {r['title'][:54].replace('|', chr(92)+'|')} |")
        L.append('')

    (OUT / 'TO-IDENTIFY.md').write_text('\n'.join(L))
    print(f'{len(todo)} unidentified -> {OUT}/TO-IDENTIFY.md')


if __name__ == '__main__':
    main()
