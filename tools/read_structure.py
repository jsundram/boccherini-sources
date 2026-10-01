# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Read a print's own headings and propose what is in it. Proposes; never decides.

    uv run tools/read_structure.py digitizations/G245-247/990005886_D-B_livr2
    uv run tools/read_structure.py --all --flagged       # everything the audit flagged

An engraved part-book says what it is at the top of every page: the part on the centre of
each leaf (`VIOLINO I°`), the work at each new quartet (`IV. QUATUOR`), and the tempo beside
it (`Allegro Molto`). `tesseract` reads all three off an 18th-century engraving well enough
to use -- noisily, so everything here is fuzzy-matched rather than parsed.

That gives the structure: where each part-book starts, where each work starts, how many
works there are. Structure is the part that was wrong about Op. 58, where two books of three
quartets were both recorded as six.

Naming the works is the harder half, and this only narrows it. RISM's incipits carry a tempo
caption per movement, and **80 of 82 Gérard numbers have a unique (tempo, key, metre)
first-movement signature**; on tempo alone, **67 of 77 are unique within their own opus**.
So a tempo read off the page usually picks one candidate out of a set of six -- and when it
does not, it says so rather than guessing. Four of Pleyel's twelve oeuvre 39 quartets have
no RISM incipit at all and can never be matched this way.

Output is a proposal to check with `contact_sheet.py`, then record as `contents_verified`.
"""
import argparse, collections, difflib, json, os, re, subprocess, sys, tempfile
from pathlib import Path

DIG = Path('digitizations')
PARTS = {
    'violino primo': 'violin 1', 'violino i': 'violin 1', 'violino 1': 'violin 1',
    'violin primo': 'violin 1', 'principale': 'violin 1',
    'violino secondo': 'violin 2', 'violino ii': 'violin 2', 'violino 2': 'violin 2',
    'viola': 'viola', 'alto': 'viola', 'violetta': 'viola', 'taille': 'viola',
    'violoncello': 'cello', 'violoncelle': 'cello', 'basso': 'bass', 'basse': 'bass',
}
TEMPO = ['allegro', 'allegro molto', 'allegro assai', 'allegro vivo', 'allegro comodo',
         'allegro con moto', 'allegro con spirito', 'allegro bizarro', 'allegro giusto',
         'allegro moderato', 'allegretto', 'allegretto moderato', 'andante', 'andantino',
         'andante sostenuto', 'andante lento', 'adagio', 'largo', 'larghetto', 'grave',
         'presto', 'prestissimo', 'moderato', 'moderato assai', 'minuetto', 'rondo',
         'tempo di minuetto', 'con spirito', 'comodo', 'affettuoso', 'amoroso', 'maestoso']
ROMAN = {'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6, 'vii': 7, 'viii': 8,
         '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6}
WORKWORD = re.compile(r'quartett|quatuor|quartetto|quartettino', re.I)


def ocr_zones(d, dpi=150, band=0.12, limit=90):
    """[(page, {zone: text})] -- the heading band OCR'd in three columns.

    Position is what tells the marks apart, and reading the band as one line loses it. On
    an engraved part-book leaf:

      outer   the page number, in the top outer corner. A bare roman numeral here is a
              folio, not a work -- accepting those turned a 52-page book into 30 works.
      inner   the work heading and its tempo, left of centre: `IV. QUATUOR  Allegro Molto`.
      centre  the part, centred: `VIOLINO I°`.

    So each zone is OCR'd separately and its text is only allowed to mean what that
    position can mean."""
    from PIL import Image
    # Munich's IIIF pages run to ~700 megapixels; Pillow refuses those by default as a
    # decompression-bomb guard. They are our own files, and only a thin strip is used.
    Image.MAX_IMAGE_PIXELS = None
    pdfs = [p for p in sorted(d.glob('*.pdf')) if 'cover' not in p.stem.lower()]
    jp = sorted(d.glob('*.jpg'))
    out = []
    # macOS tempfile hands back `/tmp/...`, a symlink; a subprocess reading through it is
    # refused, and tesseract then exits 1 with no output -- indistinguishable from a blank
    # page. Resolve it.
    with tempfile.TemporaryDirectory() as _td:
        td = os.path.realpath(_td)
        srcs = []
        if jp:
            srcs = [(p.name, p) for p in jp[:limit]]
        else:
            for pdf in pdfs:
                n = limit - len(srcs)
                if n <= 0: break
                subprocess.run(['pdftoppm', '-f', '1', '-l', str(n), '-r', str(dpi), '-jpeg',
                                str(pdf), f'{td}/{pdf.stem}'], capture_output=True, timeout=1800)
                srcs += [(f'{pdf.stem}:{p.name.rsplit("-", 1)[-1].split(".")[0]}', p)
                         for p in sorted(Path(td).glob(f'{pdf.stem}-*.jpg'))]
        for lab, f in srcs[:limit]:
            zones = {}
            try:
                im = Image.open(f)
                # Decode at reduced scale. Munich's pages are ~700 megapixels and only the
                # top eighth is wanted; full decoding made the pass take hours. `draft`
                # asks the JPEG decoder for a smaller DCT scale, which is nearly free.
                tw = 1700
                if im.width > tw * 1.6:
                    im.draft('L', (tw, int(im.height * tw / im.width)))
                im = im.convert('L')
                w, h = im.size
                top = im.crop((0, 0, w, int(h * band)))
                # The whole band reads far better than any narrow crop -- tesseract wants
                # context. So read it whole, and read the outer corners separately only to
                # learn which tokens are the folio number, so they can be discounted.
                def read(box, name):
                    c = top.crop(box).point(lambda v: 0 if v < 150 else 255)
                    if c.width < 8 or c.height < 8: return ''
                    sp = Path(td) / f'z_{name}.png'
                    c.save(sp)
                    r = subprocess.run(['tesseract', str(sp), '-', '--psm', '6'],
                                       capture_output=True, timeout=120)
                    return ' '.join(r.stdout.decode('utf-8', 'replace').split())

                zones['full'] = read((0, 0, w, top.height), 'full')
                # The corners exist only to tell a folio number from a work number, so read
                # them only when the band actually contains something numeral-shaped. That
                # is a minority of pages, and it cuts the OCR calls per page from four to
                # one on the rest.
                if re.search(r'\b[ivxIVX]{1,3}\b|\b\d{1,3}\b', zones['full']):
                    zones['outer-l'] = read((0, 0, int(w * .13), top.height), 'ol')
                    zones['outer-r'] = read((int(w * .87), 0, w, top.height), 'or')
            except Exception as e:
                print(f'  ! OCR {lab}: {type(e).__name__}: {e}', file=sys.stderr)
            out.append((lab, zones))
    return out


def fuzzy(word, vocab, cutoff=0.78):
    m = difflib.get_close_matches(word, vocab, n=1, cutoff=cutoff)
    return m[0] if m else None


def read_zones(zones):
    """(part, work_number, tempo) from the positioned reads.

    A numeral only counts as a work number when it appears in the `inner` zone -- the
    heading, left of centre -- and never from the outer corners, which carry folio numbers.
    The part is read from the centre. The tempo may sit in either inner or centre."""
    def toks(z):
        return re.sub(r'[^a-z0-9 ]', ' ', (zones.get(z) or '').lower()).split()

    # Whatever the outer corners say is the folio number, not the music.
    corner = set(toks('outer-l')) | set(toks('outer-r'))

    part = None
    for z in ('full',):
        t = toks(z)
        for n in (2, 1):
            for i in range(len(t) - n + 1):
                hit = fuzzy(' '.join(t[i:i + n]), list(PARTS), 0.8)
                if hit: part = PARTS[hit]; break
            if part: break
        if part: break

    inner = [t for t in toks('full') if t not in corner]
    nearword = bool(WORKWORD.search(zones.get('full') or '')) or any(
        difflib.SequenceMatcher(None, t, 'quatuor').ratio() > 0.6 or
        difflib.SequenceMatcher(None, t, 'quartetto').ratio() > 0.6 for t in inner)
    num = None
    if nearword:
        for t in inner:
            c = re.sub(r'[^ivx0-9]', '', t)
            if c in ROMAN and len(c) <= 3:
                num = ROMAN[c]; break

    tempo = None
    for z in ('full',):
        t = toks(z)
        for n in (3, 2, 1):
            for i in range(len(t) - n + 1):
                hit = fuzzy(' '.join(t[i:i + n]), TEMPO, 0.82)
                if hit and (tempo is None or len(hit) > len(tempo)): tempo = hit
    return part, num, tempo


def incipit_index():
    """G -> first-movement tempo caption, from the harvested incipits."""
    first = {}
    try:
        rows = [json.loads(l) for l in open('boccherini-rism-incipits.jsonl')]
    except Exception:
        return {}
    for r in rows:
        g = str(r.get('gerard') or '')
        if not g.isdigit(): continue
        mv = r.get('mvt') or ''
        if g not in first or mv < first[g][0]:
            first[g] = (mv, (r.get('caption') or '').strip().lower().rstrip('.'))
    return {g: c for g, (_, c) in first.items()}


TOOL = 'read_structure.py/2026-09-29'
STORE = Path('structure')


def is_print(m):
    return (m.get('medium') == 'print' or m.get('record_type') == 'print'
            or 'Print' in (m.get('source_types') or []))


def rism_facts(m):
    """What RISM says about this item's shape, for the machine reading to be checked against."""
    ext = ' '.join(filter(None, [m.get('holding_extent'), ' '.join(m.get('extent') or [])]))
    n = None
    mm = re.search(r'(\d+)\s*parts?\b', ext, re.I)
    if mm: n = int(mm.group(1))
    form = 'score' if re.search(r'\bscore\b|partitur', ext, re.I) else \
           'parts' if re.search(r'\bparts?\b|stimm', ext, re.I) else None
    gs = [str(x) for x in (m.get('gerard_numbers') or [])] or \
         ([str(m['gerard'])] if m.get('gerard') else [])
    return dict(extent=ext.strip() or None, parts_declared=n, form_declared=form,
                works_declared=len(gs), gerard=gs,
                source_ids=sorted({str(m['source_id'])} if m.get('source_id') else set()))


def score(facts, books, works):
    """Disagreements worth acting on. Precision over recall, deliberately.

    An earlier version also compared the number of work starts against works x part-books.
    That fired on 30 of 47 items -- not because 30 were mislabelled, but because detecting a
    work start needs OCR to recognise the engraved word QUATUOR, which it usually cannot. A
    flag that fires on two thirds of everything is not a flag. Work starts are still
    recorded as observations; they are just not evidence of anything on their own."""
    notes = []
    n = len(books)
    if facts['form_declared'] == 'score' and n > 1:
        notes.append(f'RISM calls this a score, but {n} part names were read off the pages')
    if facts['parts_declared'] and n and abs(n - facts['parts_declared']) >= 2:
        notes.append(f"RISM says {facts['parts_declared']} parts; {n} part-book starts were "
                     f"read (one either way is usually a mis-split; two is not)")
    if facts['form_declared'] == 'parts' and n == 1:
        notes.append('RISM calls this a part-set, but only one part name was read — this may '
                     'be a single part-book rather than the whole set')
    if not books and not works:
        notes.append('nothing read — faint engraving, or not a printed part-book at all')
    return notes


def source_mtime(d):
    """The newest page file an item holds. Recorded inside the reading so currency is a
    fact the reading states, not a guess from its own timestamp: a re-read that produces
    identical bytes is correctly not written, which left the file looking older than the
    PDF forever and re-OCRed 35 items on every single build."""
    ts = [x.stat().st_mtime for x in d.iterdir()
          if x.suffix.lower() in ('.pdf', '.jpg', '.jpeg', '.png')]
    return int(max(ts)) if ts else 0


def store(f, rec):
    """Write a reading only when it differs. Rewriting an identical file still moves its
    mtime, and the pipeline judges staleness by mtime -- an unconditional rewrite here made
    every later stage look dirty on every build. Returns True if the file changed."""
    body = json.dumps(rec, indent=1, ensure_ascii=False)
    if f.exists() and f.read_text() == body:
        return False
    f.write_text(body)
    return True


def rescore_all():
    """Recompute disagreements from stored readings, without re-reading the pages.

    This is the point of keeping observation and interpretation apart: when the rules
    change -- and they have -- the OCR does not have to run again."""
    n = 0
    for f in sorted(STORE.glob('*.json')):
        r = json.loads(f.read_text())
        if not r.get('read'):
            continue
        obs = r['observed']
        r['disagreements'] = score(r['rism'], obs['part_books'], obs['work_starts'])
        n += store(f, r)
    return n


def analyse(d, verbose=False, write=False):
    m = json.loads((d / 'metadata.json').read_text())
    facts = rism_facts(m)
    caps = incipit_index()

    if not is_print(m):
        # Recorded, not skipped silently: a manuscript yields nothing to OCR, and the store
        # should say so rather than leave a hole that looks like an unread item.
        rec = dict(folder=str(d.relative_to(DIG)), scan_id=d.name, tool=TOOL, read=False,
                   reason='manuscript — OCR reads engraving, not handwriting', rism=facts,
                   source_mtime=source_mtime(d), verified=m.get('contents_verified'))
        if write:
            STORE.mkdir(exist_ok=True)
            store(STORE / f'{d.name}.json', rec)
        print(f'  skip (manuscript)  {d.relative_to(DIG)}')
        return rec

    reads = ocr_zones(d)
    rows = [(lab, *read_zones(z), z) for lab, z in reads]
    books, works, seen = [], [], None
    for i, (lab, part, num, tempo, z) in enumerate(rows):
        if part and part != seen:
            books.append(dict(page=i + 1, label=lab, part=part)); seen = part
        if num:
            cands = [g for g in facts['gerard'] if caps.get(g) and tempo
                     and difflib.SequenceMatcher(None, caps[g], tempo).ratio() > 0.8]
            works.append(dict(page=i + 1, label=lab, numeral=num, tempo=tempo,
                              candidates=cands))

    notes = score(facts, books, works)
    rec = dict(folder=str(d.relative_to(DIG)), scan_id=d.name, tool=TOOL, read=True,
               pages_examined=len(rows), rism=facts, source_mtime=source_mtime(d),
               observed=dict(part_books=books, work_starts=works,
                             n_part_books=len(books), n_work_starts=len(works)),
               disagreements=notes, verified=m.get('contents_verified'))
    if write:
        STORE.mkdir(exist_ok=True)
        store(STORE / f'{d.name}.json', rec)

    print(f'\n=== {d.relative_to(DIG)}')
    print(f"    declared: G {m.get('gerard_label')} · {facts['works_declared']} works · "
          f"{facts['extent'] or 'no extent in RISM'}")
    print(f"    part-books: {len(books)}  "
          + ', '.join(f"{b['part']}@{b['page']}" for b in books))
    for w in works:
        g = w['candidates']
        note = ('-> G ' + g[0]) if len(g) == 1 else \
               ('ambiguous: G ' + ', '.join(g)) if g else \
               ('no incipit match' if w['tempo'] else 'no tempo read')
        print(f"      p{w['page']:<4} {str(w['tempo'] or '?'):24} {note}")
    for x in notes:
        print(f'    ! {x}')
    if verbose:
        for lab, part, num, tempo, z in rows:
            print(f"      {lab:22} {str(part):9} {str(num):4} {str(tempo):20} "
                  f"{(z.get('full') or '')[:48]}")
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('dirs', nargs='*', type=Path)
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--write', action='store_true', help='store the reading in structure/')
    ap.add_argument('--all', action='store_true', help='every item on disk')
    ap.add_argument('--rescore', action='store_true',
                    help='recompute disagreements from stored readings, no OCR')
    ap.add_argument('--force', action='store_true',
                    help='re-read even items whose stored reading is already current')
    a = ap.parse_args()
    if a.rescore:
        print(f'{rescore_all()} reading(s) changed', file=sys.stderr)
        return
    dirs = list(a.dirs)
    if a.all:
        dirs = [f.parent for f in sorted(DIG.rglob('metadata.json'))
                if [x for x in f.parent.iterdir()
                    if x.suffix.lower() in ('.pdf', '.jpg')]]
        if not a.force:
            # Only what has actually changed. `--all` re-OCRed all 78 prints whenever any
            # item was touched, so adding six manuscripts -- which OCR cannot read at all --
            # cost forty-six minutes and produced identical output for every other item.
            fresh, n = [], 0
            for d in dirs:
                rec = STORE / f'{d.name}.json'
                try:
                    was = json.loads(rec.read_text()).get('source_mtime')
                except Exception:
                    was = None
                if was and was == source_mtime(d):
                    n += 1
                else:
                    fresh.append(d)
            dirs = fresh
            print(f'{n} reading(s) already current, {len(dirs)} to read', file=sys.stderr)
    for d in dirs:
        try:
            analyse(d, a.verbose, a.write)
        except Exception as e:
            print(f'  ! {d}: {type(e).__name__}: {e}', file=sys.stderr)


if __name__ == '__main__':
    main()
