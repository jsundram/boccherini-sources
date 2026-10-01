# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy"]
# ///
"""Build a plate catalogue of the facsimiles on disk -> boccherini_sources.html

    uv run tools/build_sources_page.py

Companion to `build_page.py`, which engraves what RISM *indexed*. This one shows what
we actually *have*: every scan under `digitizations/`, with a thumbnail of its first
page, keyed on the same Gérard spine from `opera.json`.

Two provenances, kept visibly apart because they mean different things:

  linked   RISM's MARC 856 pointed at it (`rism_digitizations.py`)
  (a source found by searching a library portal is shelved exactly like one RISM links --
  how it was found is a fact about us, not about the source, and belongs in the docs)

Thumbnails come from the first page of each item — Pillow for JPEG runs, `pdftoppm`
for the Rochester part-PDFs — and are embedded as data URIs, so the page is one file.
"""
import base64, html, io, json, pathlib, re, subprocess, sys, urllib.parse
import evidence
from collections import defaultdict
from pathlib import Path

DIG = Path('digitizations')
OUT = Path('boccherini_sources.html')
THUMB_W = 150
PREVIEW_W = 620      # the hover/tap enlargement -- big enough to judge a scan by
SCAN_PAGES = 12      # how deep to look for a usable opening page
MEDIUM = {'autograph': 'Autograph', 'manuscript': 'Manuscript copy', 'print': 'Print'}


def gnum(g):
    m = re.match(r'\s*(?:No\.?\s*)?(\d+)(.*)', g or '')
    return (int(m[1]), m[2].strip()) if m else (10**9, g or '￿')


def medium_of(m):
    """One vocabulary across both provenances. RISM's 593 $a is authoritative where it
    exists; Gallica's is read off its own title, so it is a weaker reading of the same thing."""
    t = (m.get('source_type') or '') + ' ' + ' '.join(m.get('source_types') or []) \
        + ' ' + (m.get('medium') or '')
    if m.get('is_autograph') or 'utograph' in t: return 'autograph'
    if 'anuscript' in t: return 'manuscript'
    return 'print'


def page_stats(im):
    """Cheap descriptors of one page, enough to tell a title page from the things
    libraries put in front of it."""
    import numpy as np
    im = im.convert('RGB')
    w, h = im.size
    s = im.resize((160, max(1, round(160 * h / w))))
    a = np.asarray(s).astype('float32')
    g = a.mean(2)
    bg = float(np.percentile(g, 90))
    mask = g > bg - 12
    half = g.shape[1] // 2
    def edge(x):
        return float((abs(x[:, 1:] - x[:, :-1]).mean() + abs(x[1:] - x[:-1]).mean()) / 2)
    # How many *different* colours the page is made of. A calibration chart is a grid of
    # unlike blocks; a blue paper cover is one hue however dark it is, which is why an
    # ink-density test confused the two.
    bh, bw = max(1, a.shape[0] // 6), max(1, a.shape[1] // 6)
    cells = np.array([a[i * bh:(i + 1) * bh, j * bw:(j + 1) * bw].reshape(-1, 3).mean(0)
                      for i in range(6) for j in range(6)])
    return dict(
        uniq=float(np.linalg.norm(cells - cells.mean(0), axis=1).mean()),
        bg=bg, ink=float((g < bg - 45).mean()), edge=edge(g),
        sat=float((a.max(2) - a.min(2)).mean()),
        noise=float(g[mask].std()) if mask.sum() > 50 else 0.0,
        left=edge(g[:, :half]), right=edge(g[:, half:]), ar=w / h)


def skip_reason(st):
    """Why this page is not worth showing. None means it is fine.

    The thumbnail has one job: say what the reproduction looks like. A cover cannot do
    that however handsome it is, so covers are rejected along with blanks and the things
    libraries put in front of a scan. Measured on the actual offenders, after cropping --
    an uncropped page scores low simply for having wide margins."""
    if st['uniq'] > 85 and st['edge'] < 8:
        return 'a scan calibration target'
    if st['bg'] >= 252 and st['noise'] < 2.4 and st['ink'] < 0.15 and st['sat'] < 8:
        # Born digital: pure white, no paper grain, sparse text. A photographed white
        # title page always carries grain (2.6-3.7 here) or far more ink.
        return 'a library cover sheet'
    if st['ink'] > 0.60:
        # Most of the page far darker than its own paper tone: marbled boards, a blue
        # paper wrapper, a leather binding. Writing on paper never reaches this.
        return 'a cover, not a page of the music'
    if st['bg'] < 172:
        # The support itself is dark: cloth and leather bindings, marbled boards, the
        # marbled endpapers behind them. Music and title pages are ink on light paper --
        # the darkest legitimate one measured here is Eichstätt's at 176.
        return 'a binding or endpaper'
    if st['edge'] < 5.0:
        return 'blank, or a plain cover with nothing to judge'
    return None


def pdf_order(d):
    """The PDFs of an item, least cover-like first.

    Rochester ships a separate one-page photograph of the binding beside each part --
    `39087009315161.cello._color_cover.pdf` -- and it sorts first. Taking page 1 of the
    first PDF therefore showed the leather rather than the music, with no later page to
    fall through to, because the file is one page long."""
    # Part order, not alphabetical order. Rochester ships one PDF per part, and sorting by
    # name opens on the cello -- `...cello.pdf` precedes `...violin1.pdf`. A part-set is
    # conventionally read from the first violin, and it is the part a reader recognises.
    rank = {'violin1': 0, 'vl1': 0, 'v1': 0, 'violino1': 0,
            'violin2': 1, 'vl2': 1, 'v2': 1,
            'viola': 2, 'tenor': 2, 'vla': 2, 'va': 2,
            'cello': 3, 'violoncello': 3, 'vlc': 3, 'vc': 3, 'basso': 3, 'b': 3}
    def key(x):
        tag = x.stem.rsplit('.', 1)[-1].lower().replace('_', '').replace(' ', '')
        return ('cover' in x.stem.lower(), rank.get(tag, 9), x.stem)
    return sorted(d.glob('*.pdf'), key=key)


def _cells(im, ny=18, nx=18):
    """Edge energy on a grid -- writing lights cells up, blank paper and mount board do not."""
    import numpy as np
    w, h = im.size
    g = np.asarray(im.convert('L').resize((240, max(1, round(240 * h / w))))).astype('float32')
    e = np.zeros_like(g)
    e[:-1] += np.abs(np.diff(g, axis=0))
    e[:, :-1] += np.abs(np.diff(g, axis=1))
    ch, cw = max(1, e.shape[0] // ny), max(1, e.shape[1] // nx)
    return np.array([[e[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw].mean()
                      for j in range(nx)] for i in range(ny)])


def bright_box(im):
    """Crop a dark surround away, keeping the lit page.

    The Library of Congress photographs each opening on a cream mount against a dark
    table. Finding the bright subject is what separates that from an ordinary scan: on a
    full-bleed scan the bright region is the whole frame and nothing is cropped."""
    import numpy as np
    w, h = im.size
    g = np.asarray(im.convert('L').resize((200, max(1, round(200 * h / w))))).astype('float32')
    lo, hi = float(np.percentile(g, 8)), float(np.percentile(g, 92))
    if hi - lo < 60:
        return None
    ys, xs = np.where(g > (lo + hi) / 2)
    if len(ys) < 200:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    frac = ((y1 - y0 + 1) * (x1 - x0 + 1)) / (g.shape[0] * g.shape[1])
    if frac > 0.86 or frac < 0.08:
        return None
    sx, sy = w / g.shape[1], h / g.shape[0]
    return (max(0, int(x0 * sx)), max(0, int(y0 * sy)),
            min(w, int(x1 * sx)), min(h, int(y1 * sy)))


def content_box(im):
    """Crop to where the detail is.

    One mechanism for problems that reduce to the same thing -- the interesting part of the
    frame is smaller than the frame. A double-page opening with a blank verso, a manuscript
    photographed on a cream mount against a dark table, a page with wide margins.

    Two passes, because a blank verso is not caught by a bounding box: the ruled border of
    the empty page lights up cells at the far edge, so the box spans everything. Dropping a
    near-empty half first, then boxing what remains, handles both.

    Returns None when the detail already fills the frame, which is the ordinary case."""
    import numpy as np
    w, h = im.size
    cells = _cells(im)
    if cells.max() <= 0:
        return None
    ny, nx = cells.shape
    active = cells > max(cells.max() * 0.18, 1.5)
    if active.sum() < 4:
        return None
    x_lo, x_hi = 0, nx
    half = nx // 2
    left, right = active[:, :half].sum(), active[:, half:].sum()
    if max(left, right) >= 6 and min(left, right) <= max(left, right) * 0.28:
        if right > left:
            x_lo = half
        else:
            x_hi = half
        active = active[:, x_lo:x_hi]
        if active.sum() < 4:
            return None
    ys, xs = np.where(active)
    frac = (((ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)) / (ny * nx)
            * ((x_hi - x_lo) / nx))
    if frac > 0.80 and x_lo == 0 and x_hi == nx:
        return None
    pad = 0.6
    y0 = max(0.0, ys.min() - pad) / ny
    y1 = min(float(ny), ys.max() + 1 + pad) / ny
    x0 = (x_lo + max(0.0, xs.min() - pad)) / nx
    x1 = (x_lo + min(float(x_hi - x_lo), xs.max() + 1 + pad)) / nx
    box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    # Refuse a crop that keeps only a sliver. On an otherwise empty leaf the one bright
    # thing is the shelfmark label, and zooming to it makes a thumbnail of a sticker.
    keep = ((box[2] - box[0]) * (box[3] - box[1])) / float(w * h)
    if keep < 0.22:
        return None
    return box if box[2] - box[0] > w * 0.12 and box[3] - box[1] > h * 0.12 else None
    """Crop to where the detail is.

    One mechanism for three problems that all reduce to the same thing -- the interesting
    part of the frame is smaller than the frame. A double-page opening with a blank verso,
    a manuscript photographed on a cream mount against a dark table, a page with wide
    margins. Writing has edge energy; blank paper, mount board and table do not, so the
    bounding box of the high-energy cells is the page worth showing.

    Returns None when the detail already fills the frame, which is the ordinary case."""
    import numpy as np
    w, h = im.size
    g = np.asarray(im.convert('L').resize((240, max(1, round(240 * h / w))))).astype('float32')
    gy, gx = np.abs(np.diff(g, axis=0)), np.abs(np.diff(g, axis=1))
    e = np.zeros_like(g)
    e[:-1] += gy
    e[:, :-1] += gx
    ny, nx = 18, 18
    ch, cw = max(1, e.shape[0] // ny), max(1, e.shape[1] // nx)
    cells = np.array([[e[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw].mean()
                       for j in range(nx)] for i in range(ny)])
    if cells.max() <= 0:
        return None
    active = cells > max(cells.max() * 0.18, 1.5)
    if active.sum() < 4:
        return None
    ys, xs = np.where(active)
    frac = ((ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)) / (ny * nx)
    if frac > 0.80:
        return None
    pad = 0.6
    y0 = max(0.0, ys.min() - pad) / ny
    y1 = min(float(ny), ys.max() + 1 + pad) / ny
    x0 = max(0.0, xs.min() - pad) / nx
    x1 = min(float(nx), xs.max() + 1 + pad) / nx
    box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    return box if box[2] - box[0] > w * 0.12 and box[3] - box[1] > h * 0.12 else None


def candidates(d, n=SCAN_PAGES, only=None):
    """(label, PIL image) for the first few pages, however the item is stored.

    Spans PDFs: a one-page cover file must not exhaust the search."""
    from PIL import Image
    # Munich's pages are 210 megapixels, over Pillow's 179 MP bomb guard. Without this the
    # open raises, the bare except below turned it into None, and four livraisons rendered
    # "no preview" with nothing anywhere saying why. `read_structure.py` does the same.
    Image.MAX_IMAGE_PIXELS = None
    jp = sorted(d.glob('*.jpg'))
    if jp:
        return [(p.name, Image.open(p)) for p in jp[:n]]
    import tempfile, os
    out = []
    for pdf in ([only] if only else pdf_order(d)):
        if len(out) >= n:
            break
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(['pdftoppm', '-f', '1', '-l', str(n - len(out)), '-r', '30',
                            '-jpeg', str(pdf), os.path.join(td, 'p')],
                           capture_output=True, timeout=180, check=False)
            for f in sorted(pathlib.Path(td).glob('p*.jpg')):
                out.append((f'{pdf.stem}:{f.name}', Image.open(f).copy()))
    return out


def render(d, label, width):
    """The chosen page again, at a size worth looking at. `label` is what candidates()
    called it -- a filename for a jpg run, `<pdf stem>:p-NN.jpg` for a PDF."""
    from PIL import Image
    jp = sorted(d.glob('*.jpg'))
    if jp:
        f = d / label
        return Image.open(f) if f.exists() else None
    stem, _, page = label.rpartition(':')
    pdf = next((x for x in pdf_order(d) if x.stem == stem), None)
    if pdf is None:
        return None
    n = int(re.sub(r'\D', '', page) or 1)
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(['pdftoppm', '-f', str(n), '-l', str(n), '-r', '110', '-jpeg',
                        '-singlefile', str(pdf), os.path.join(td, 'p')],
                       capture_output=True, timeout=120, check=False)
        f = pathlib.Path(td) / 'p.jpg'
        return Image.open(f).copy() if f.exists() else None


def encode(im, width, quality):
    from PIL import Image
    w, h = im.size
    if w > width:
        im = im.resize((width, max(1, round(h * width / w))), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert('RGB').save(buf, 'JPEG', quality=quality, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode(), im.width, im.height


OVERRIDES = [None]


def overrides():
    if OVERRIDES[0] is None:
        try:
            OVERRIDES[0] = {k: v for k, v in
                            json.loads(Path('thumbnails.json').read_text()).items()
                            if not k.startswith('_')}
        except Exception:
            OVERRIDES[0] = {}
    return OVERRIDES[0]


def thumb(d, only=None):
    """(small, big, note) -- the opening page worth showing, small for the grid and
    large for the hover preview."""
    try:
        cands = candidates(d, only=only)
    except Exception as ex:
        print(f'  ! preview {d.name}: {type(ex).__name__}: {ex}', file=sys.stderr)
        return None
    if not cands:
        return None
    ov = overrides().get(d.name)
    if ov:
        i = max(0, int(ov.get('page', 1)) - 1)
        if i < len(cands):
            full = render(d, cands[i][0], PREVIEW_W) or cands[i][1]
            c = ov.get('crop')
            if c:
                w, h = full.size
                full = full.crop((int(c[0] * w), int(c[1] * h), int(c[2] * w), int(c[3] * h)))
            try:
                small = encode(full, THUMB_W, 58)
                big = encode(full, PREVIEW_W, 62)
                return dict(src=small[0], w=small[1], h=small[2], big=big[0],
                            note=ov.get('note') or 'hand-set')
            except Exception:
                return None
    chosen, note = None, None
    for i, (label, im) in enumerate(cands):
        try:
            probe = im
            bb = bright_box(probe)
            if bb: probe = probe.crop(bb)
            cb = content_box(probe)
            if cb: probe = probe.crop(cb)
            st = page_stats(probe)
        except Exception:
            continue
        why = skip_reason(st)
        if why is None:
            chosen = (i, label, im)
            break
        if note is None:
            note = why                       # remember why page 1 was rejected
    if chosen is None:                       # nothing passed -- show page 1 and say so
        chosen = (0, cands[0][0], cands[0][1])
        note = 'no page passed the checks'
    i, label, im = chosen
    if i > 0 and note:
        note = f'page {i + 1}; page 1 is {note}'
    elif i > 0:
        note = f'page {i + 1}'
    else:
        note = None
    try:
        full = render(d, label, PREVIEW_W) or im
        cropped = False
        bb = bright_box(full)
        if bb:
            full = full.crop(bb); cropped = True
        cb = content_box(full)
        if cb:
            full = full.crop(cb); cropped = True
        if cropped:
            note = ((note + '; ') if note else '') + 'cropped to the page'
        small = encode(full, THUMB_W, 58)
        big = encode(full, PREVIEW_W, 62)
        return dict(src=small[0], w=small[1], h=small[2], big=big[0], note=note)
    except Exception as ex:
        print(f'  ! preview {d.name}: {type(ex).__name__}: {ex}', file=sys.stderr)
        return None


def pdf_link(it):
    """The item's id, linking to the PDF on disk so a card leads to the file.

    Relative to this page, which sits at the repository root, so it opens from a browser
    looking at the local file. Printing the whole path instead cost a line of every card for
    something only wanted on the way to opening it.
    """
    pdfs = sorted(it['dir'].glob('*.pdf'))
    want = it.get('only') or next((x for x in pdfs if '.' not in x.stem), None) or \
        (pdfs[0] if pdfs else None)
    name = e(it['dir'].name)
    if not want:
        return f'<p class="path">{name}</p>'
    href = '/'.join(urllib.parse.quote(part) for part in want.parts)
    return (f'<p class="path"><a href="{href}" target="_blank" rel="noopener" '
            f'title="{e(str(want))}">{name}</a></p>')


def scan_link(m, gallica):
    """(href, label) for the button, or None when there is nowhere honest to send anyone.

    `source` holds a portal *name* -- "gallica", "bne", "private-photography" -- for anything
    not fetched from a URL, and using it as an href rendered
    `file:///.../private-photography`. A scan made in a reading room has no library page to
    open; its RISM record is the honest destination, labelled as the record and not as a scan.
    """
    if gallica and m.get('ark'):
        return (m['ark'], 'open the scan')
    for k in ('url', 'manifest', 'ark', 'mets', 'bne_digital_url'):
        v = m.get(k)
        if isinstance(v, str) and '://' in v:
            return (v, 'open the scan')
    v = m.get('source')
    if isinstance(v, str) and '://' in v and '/sources/' not in v:
        return (v, 'open the scan')
    for u in rism_urls(m) or []:
        if isinstance(u, str) and '://' in u:
            return (u, 'the RISM record')
    return None


def entry(d, m, gallica, pdfs, pages, only=None, **over):
    """One shelf entry. `over` replaces any field — a per-work entry overrides the
    Gérard fields and previews only its own PDF."""
    return dict(
        dir=d, gallica=gallica,
        # A correction supplies `gerard_numbers` from the volume's contents but leaves
        # `gerard` as RISM had it -- often None. Fall back, or the item falls off the spine.
        gerard=m.get('gerard') or next(iter(m.get('gerard_numbers') or []), None),
        # A complete-opus print carries all six GerB numbers; show the span, not the
        # single one it happens to be filed under.
        glabel=m.get('gerard_label') or m.get('gerard'),
        gnums=m.get('gerard_numbers') or [],
        title=m.get('title'),
        siglum=m.get('siglum') or ('BnF' if gallica else None),
        institution=m.get('institution'),
        shelfmark=m.get('shelfmark'),
        former=m.get('former_shelfmark'),
        medium=medium_of(m),
        not_quartet=m.get('form') == 'not-a-quartet',
        tier=evidence.tier_of(m, evidence.reading(d.name)),
        checked=m.get('contents_verified') or None,
        medium_note=m.get('medium_established_by'),
        date=((m.get('published') or {}).get('date') or m.get('date')
              or m.get('date_statement') or m.get('year')),
        publisher=(m.get('published') or {}).get('publisher') or m.get('publisher'),
        place=(m.get('published') or {}).get('place') or m.get('publication_place'),
        plates=', '.join(m.get('plate_numbers') or []),
        extent=m.get('holding_extent') or ', '.join(m.get('extent') or []),
        scoring=m.get('scoring'),
        incipits=m.get('incipits'),
        rism=rism_urls(m),
        rism_relation=m.get('rism_relation'),
        link=scan_link(m, gallica),
        n_img=len(pages),
        # A PDF whose stem carries no '.' suffix is the whole book, not a part:
        # `CZ-Pu_59_R_23.pdf` beside `CZ-Pu_59_R_23.cello.pdf`.
        n_pages_pdf=pdf_pages(pdfs),
        n_whole=len([x for x in pdfs if '.' not in x.stem]),
        n_pdf=len([x for x in pdfs if '.' in x.stem]),
        by_hand=bool(m.get('downloaded_by_hand')),
        parts=parts_label(m, pdfs),
        thumb=thumb(d, only=only),
        only=only,
    ) | over


def items():
    """Every downloaded item, from its metadata.json sidecar."""
    out = []
    for f in sorted(DIG.rglob('metadata.json')):
        d = f.parent
        if d.name == 'watermarks': continue
        try:
            m = json.loads(f.read_text())
        except Exception:
            continue
        pages = sorted(d.glob('*.jpg'))
        pdfs = sorted(d.glob('*.pdf'))
        if not pages and not pdfs: continue                 # nothing was fetched
        gallica = m.get('source') == 'gallica'
        # An item whose `files` map is keyed per work -- {"G248": …, "G249": …} -- holds a
        # separate PDF for each, and belongs on the shelf as one entry per work, beside the
        # other copies of those works. The folder stays single: both share one shelfmark,
        # and two folders with the same (siglum, shelfmark) collide in the concordance.
        per_work = {}
        for k, v in (m.get('files') or {}).items():
            g = re.fullmatch(r'G\s*(\d+)', str(k))
            if g and (d / str(v)).exists():
                per_work[g.group(1)] = d / str(v)
        if len(per_work) > 1:
            for gnum_, pdf in sorted(per_work.items(), key=lambda kv: int(kv[0])):
                out.append(entry(d, m, gallica, [pdf], pages,
                                 gerard=gnum_, glabel=gnum_, gnums=[gnum_],
                                 only=pdf))
            continue
        out.append(entry(d, m, gallica, pdfs, pages))
    return out


PART_ABBR = {'violin1': 'V1', 'violin2': 'V2', 'viola': 'VA', 'tenor': 'VA',
             'cello': 'VC', 'violoncello': 'VC', 'basso': 'B', 'bass': 'B'}
FULL_SET = ({'V1', 'V2', 'VA', 'VC'}, {'V1', 'V2', 'VA', 'B'})


def rism_urls(m):
    """Every RISM source this item points at.

    The sidecars grew three shapes for the same fact: a bare string, a list, and -- for the
    Library of Congress manuscripts, which RISM catalogues only at other libraries -- a dict
    keyed by Gérard number. Reading one shape lost the other two, which is why most cards
    showed no RISM link at all."""
    out = []

    def walk(v):
        if isinstance(v, str):
            if '/sources/' in v: out.append(v)
        elif isinstance(v, list):
            for x in v: walk(x)
        elif isinstance(v, dict):
            for x in v.values(): walk(x)

    for k in ('source', 'rism_related', 'rism_constituents'):
        walk(m.get(k))
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u); uniq.append(u)
    return uniq


def pdf_pages(pdfs):
    """Total pages across an item's PDFs, ignoring the separate cover photographs some
    libraries ship beside each part."""
    n = 0
    for f in pdfs:
        if 'cover' in f.stem.lower():
            continue
        try:
            out = subprocess.run(['pdfinfo', str(f)], capture_output=True, text=True,
                                 timeout=60).stdout
            n += int(next(l.split(':')[1] for l in out.splitlines() if l.startswith('Pages')))
        except Exception:
            pass
    return n


def pages_label(it):
    """How many pages. Just the number -- what form they are stored in is our business."""
    n = it['n_img']
    if not n:
        n = it.get('n_pages_pdf') or 0
    return str(n) if n else None


def parts_label(m, pdfs):
    """'parts', 'score', or which parts are actually here.

    A complete set does not need enumerating -- 'V1, V2, VA, VC' is just 'parts' spelled
    out. An incomplete one does, because which parts are missing is the whole point."""
    named = [p for p in (m.get('parts') or []) if isinstance(p, str)]
    if not named:
        named = [x.stem.split('.', 1)[-1] for x in pdfs if '.' in x.stem]
    have, ordered = set(), []
    for n in named:
        a = PART_ABBR.get(re.sub(r'[^a-z0-9]', '', n.lower()))
        if a and a not in have:
            have.add(a); ordered.append(a)
    extent = ' '.join(filter(None, (m.get('holding_extent'), ' '.join(m.get('extent') or []))))
    if have:
        if any(have >= full for full in FULL_SET) or m.get('complete') is True:
            return 'parts'
        return ', '.join(sorted(ordered, key=lambda a: ['V1', 'V2', 'VA', 'VC', 'B'].index(a)
                                if a in ('V1', 'V2', 'VA', 'VC', 'B') else 9)) + ' only'
    if re.search(r'\bscore\b|partitur', extent, re.I): return 'score'
    if re.search(r'\bparts?\b|stimm', extent, re.I): return 'parts'
    return None


def e(s):
    return html.escape(str(s)) if s not in (None, '') else ''


def card(it):
    t = it['thumb']
    img = (f'<img class="pg" src="{t["src"]}" width="{t["w"]}" height="{t["h"]}" alt="" '
           f'loading="lazy">' if t else '<div class="pg noimg">no preview</div>')
    ident = ' '.join(filter(None, (it['siglum'], it['shelfmark'])))
    # Every card carries the same rows, in the same order, whether or not we know the
    # answer. A missing field that simply vanishes reads as a different kind of object;
    # an em dash says we looked and RISM does not say.
    pub = it['publisher'] and (it['publisher'] + (f" · {it['place']}" if it['place'] else ''))
    rism = it['rism']
    rism_cell = (' '.join(f'<a href="{u}" target="_blank" rel="noopener">'
                          f'{u.rstrip("/").rsplit("/", 1)[-1]}</a>' for u in rism[:3])
                 + (f' +{len(rism) - 3}' if len(rism) > 3 else '')
                 + (' <span class="none" title="RISM catalogues this edition at other '
                    'libraries, not this copy">· edition</span>'
                    if it['rism_relation'] == 'work' else '')) if rism else \
        '<span class="none">not in RISM</span>'
    meta = [('Format', e(it['parts'])),
            ('Date', e(it['date'])),
            ('Publisher' if it['publisher'] else 'Kind',
             e(pub) if pub else MEDIUM[it['medium']]),
            ('Plate', e(it['plates'])),
            ('Pages', pages_label(it)),
            ('RISM', rism_cell),
            ('Evidence', f'<span class="tier t{it["tier"][0]}">{it["tier"][0]}</span> '
                         f'<span class="tlab">{e(it["tier"][1])}</span>')]
    rows = ''.join(f'<dt>{k}</dt><dd>{v or "<span class=\'none\'>—</span>"}</dd>'
                   for k, v in meta)
    return f'''<article class="item m-{it['medium']}" data-medium="{it['medium']}" data-prov="{'gallica' if it['gallica'] else 'linked'}" data-tier="{it['tier'][0]}" data-q="{e((ident + ' ' + (it['title'] or '') + ' ' + (it['institution'] or '') + ' ' + str(it['dir']) + ' ' + it['tier'][1] + (' checked' if it['checked'] else '')).lower())}">
  <button class="shot" type="button" data-big="{t['big'] if t else ''}"
     data-cap="{e(ident)} — {e(t['note']) if t and t['note'] else 'first page'}"
     aria-label="Enlarge">{img}</button>
  <div class="body">
    <p class="gid">{('G ' + e(it['glabel'])) if it['glabel'] else ('<span class="nog">not a quartet</span>' if it['not_quartet'] else '<span class="nog">no Gérard number</span>')}{(' · ' + str(len(it['gnums'])) + ' quartets') if len(it['gnums']) > 1 else ''}</p>
    <p class="ident"><span class="{'sig' if it['institution'] else 'sig plain'}"{(' title="' + e(it['institution']) + '" tabindex="0"') if it['institution'] else ''}>{e(it['siglum'] or '—')}</span>{(' <span class="shelf">' + e(it['shelfmark']) + '</span>') if it['shelfmark'] else ''}</p>
    <dl>{rows}</dl>
    {(f'<p class="go"><a href="{e(it["link"][0])}" target="_blank" rel="noopener">{e(it["link"][1])}</a></p>') if it['link'] else '<p class="go nolink">held here only</p>'}
    {pdf_link(it)}
  </div>
</article>'''


def main():
    if not DIG.exists(): sys.exit('no digitizations/ directory — run rism_digitizations.py first')
    opera = json.loads(Path('opera.json').read_text())
    # gerard -> (opus, year) from the same spine build_page.py uses
    spine, groups = {}, []

    def walk(x):
        if isinstance(x, dict):
            if 'opus' in x and 'quartets' in x: groups.append(x)
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(opera)
    for g in groups:
        for q in g['quartets']:
            spine[str(q.get('gerard'))] = (g.get('opus'), g.get('year'), q.get('key'))

    its = items()
    print(f'{len(its)} items with files', file=sys.stderr)
    by_opus, unplaced = defaultdict(list), []
    for it in its:
        s = spine.get(str(it['gerard'] or ''))
        (by_opus[s[0]].append(it) if s else unplaced.append(it))

    n_img = sum(i['n_img'] for i in its)
    n_pdf = sum(i['n_pdf'] for i in its)
    auto = [i for i in its if i['medium'] == 'autograph']
    ms = [i for i in its if i['medium'] == 'manuscript']
    pr = [i for i in its if i['medium'] == 'print']
    libs = {i['siglum'] for i in its if i['siglum']}
    size_gb = sum(f.stat().st_size for f in DIG.rglob('*') if f.is_file()) / 1e9

    sec, nav = [], []
    for opus in sorted(by_opus, key=lambda o: (o is None, o)):
        rows = sorted(by_opus[opus], key=lambda i: (gnum(i['gerard']), i['siglum'] or ''))
        yr = next((spine[str(r['gerard'])][1] for r in rows if str(r['gerard']) in spine), '')
        gs = sorted({g for r in rows for g in (r['gnums'] or [str(r['gerard'])]) if g}, key=gnum)
        nav.append((f'op{opus}', f'Op. {opus}', len(rows)))
        sec.append(f'''<section class="opus" id="op{e(str(opus))}"><header class="oh">
  <h3><span class="ono">Op. {e(opus)}</span> <span class="oyr">{e(yr)}</span></h3>
  <p class="og">G {e(gs[0] + '–' + gs[-1] if len(gs) > 2 and all(x.isdigit() for x in gs)
                       and int(gs[-1]) - int(gs[0]) == len(gs) - 1 else ', '.join(gs))}
     · {len(rows)} source{'s' if len(rows) != 1 else ''}</p>
</header><div class="grid">{''.join(card(i) for i in rows)}</div></section>''')

    if unplaced:
        rows = sorted(unplaced, key=lambda i: (gnum(i['gerard']), i['siglum'] or ''))
        nav.append(('offspine', 'Off the spine', len(rows)))
        sec.append(f'''<section class="opus" id="offspine"><header class="oh">
  <h3><span class="ono">Off the spine</span></h3>
  <p class="og">{len(rows)} sources whose Gérard number sits outside the 91 quartets of the
  Periodic Table, plus {sum(1 for r in rows if r['not_quartet'])} that are not quartets at all —
  kept because they were downloaded alongside the rest</p>
</header><div class="grid">{''.join(card(i) for i in rows)}</div></section>''')


    page = f'''<title>Boccherini Facsimile Shelf</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,400;6..96,600;6..96,800&family=Spectral:wght@300;400;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{
  --paper:#eceae3; --card:#f7f6f2; --sunk:#e2dfd6; --ink:#1a1c19; --ink2:#4a4d45;
  --ink3:#767a70; --rule:#d6d2c8; --link:#2f5d7c;
  --m-autograph:#8a4f1d; --m-manuscript:#35576f; --m-print:#5d5e58;
  --shadow:rgba(40,36,28,.13);
  --display:'Bodoni Moda',Didot,'Times New Roman',serif;
  --body:'Spectral',Georgia,serif;
  --mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;
}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --paper:#15171a; --card:#1e2124; --sunk:#131517; --ink:#e9e7e0; --ink2:#b3b0a7;
  --ink3:#8a8b84; --rule:#33373a; --link:#8fc0e0;
  --m-autograph:#cf9358; --m-manuscript:#7fb0d4; --m-print:#a9aaa3;
  --shadow:rgba(0,0,0,.5);
}}}}
:root[data-theme="dark"]{{
  --paper:#15171a; --card:#1e2124; --sunk:#131517; --ink:#e9e7e0; --ink2:#b3b0a7;
  --ink3:#8a8b84; --rule:#33373a; --link:#8fc0e0;
  --m-autograph:#cf9358; --m-manuscript:#7fb0d4; --m-print:#a9aaa3;
  --shadow:rgba(0,0,0,.5);
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:40px 72px}}
a{{color:var(--link)}}
a:focus-visible,button:focus-visible,input:focus-visible{{outline:2px solid var(--link);outline-offset:2px}}

.mast{{border-bottom:1px solid var(--ink);padding-bottom:22px;margin-bottom:26px}}
h1{{font-family:var(--display);font-weight:800;font-size:clamp(30px,5.2vw,58px);
  line-height:1.03;margin:0 0 10px;letter-spacing:-.015em;text-wrap:balance}}
.lede{{margin:0;max-width:64ch;color:var(--ink2);font-size:clamp(15px,1.4vw,17.5px)}}
.lede b{{color:var(--ink);font-weight:600}}

.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));
  gap:0;border:1px solid var(--rule);margin:24px 0 8px;background:var(--rule)}}
.tile{{background:var(--card);padding:13px 15px;display:flex;flex-direction:column;gap:1px;
  border-right:0}}
.tile b{{font-family:var(--display);font-size:29px;font-weight:800;line-height:1;
  font-variant-numeric:tabular-nums}}
.tile span{{font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink3)}}
.tile.a b{{color:var(--m-autograph)}} .tile.m b{{color:var(--m-manuscript)}}
.tile.p b{{color:var(--m-print)}}

.controls{{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin:26px 0 8px;
  position:sticky;top:env(safe-area-inset-top,0px);z-index:6;background:var(--paper);
  padding-block:11px;border-bottom:1px solid var(--rule)}}
input[type=search]{{font:inherit;font-size:14.5px;font-family:var(--mono);padding:7px 11px;
  border:1px solid var(--rule);background:var(--card);color:var(--ink);border-radius:2px;
  flex:1 1 190px;min-width:0}}
.chip{{font-family:var(--mono);font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;
  padding:7px 11px;border:1px solid var(--rule);background:var(--card);color:var(--ink2);
  border-radius:2px;cursor:pointer;user-select:none}}
.chip[aria-pressed=true]{{background:var(--ink);color:var(--paper);border-color:var(--ink)}}
.tally{{font-family:var(--mono);font-size:11.5px;color:var(--ink3);margin-left:auto;
  font-variant-numeric:tabular-nums}}

.opus{{margin-top:40px}}
.opus[hidden]{{display:none}}
.oh{{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 16px;
  border-bottom:1px solid var(--rule);padding-bottom:7px;margin-bottom:18px}}
.oh h3{{margin:0;font-family:var(--display);font-weight:600;font-size:clamp(20px,2.4vw,27px);
  letter-spacing:-.01em}}
.ono{{font-weight:800}}
.oyr{{font-family:var(--mono);font-size:12px;color:var(--ink3);letter-spacing:.06em}}
.og{{margin:0;font-family:var(--mono);font-size:11.5px;color:var(--ink3);letter-spacing:.03em;
  max-width:62ch;line-height:1.5;text-transform:none}}

.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:15px}}
.item{{display:flex;gap:13px;background:var(--card);border:1px solid var(--rule);
  border-left:3px solid var(--rule);padding:12px;position:relative}}
.item[hidden]{{display:none}}
.m-autograph{{border-left-color:var(--m-autograph)}}
.m-manuscript{{border-left-color:var(--m-manuscript)}}
.m-print{{border-left-color:var(--m-print)}}
.shot{{flex:0 0 auto;line-height:0;align-self:flex-start;display:block}}
.pg{{width:74px;height:auto;max-width:74px;background:var(--sunk);
  box-shadow:1px 1px 4px var(--shadow);display:block}}
.noimg{{width:74px;height:98px;display:flex;align-items:center;justify-content:center;
  text-align:center;font-family:var(--mono);font-size:9px;color:var(--ink3);
  background:var(--sunk);line-height:1.3;padding:4px}}
.body{{min-width:0;flex:1}}
.body p{{margin:0}}
.gid{{font-family:var(--display);font-weight:800;font-size:15px;letter-spacing:-.01em;
  line-height:1.2;color:var(--ink)}}
.gid .nog{{font-family:var(--mono);font-size:10.5px;font-weight:400;color:var(--ink3);
  letter-spacing:.05em;text-transform:uppercase}}
.ident{{font-family:var(--mono);font-size:13px;font-weight:500;line-height:1.35;
  word-break:break-word;margin-top:2px}}
.sig{{color:var(--ink)}}
.shelf{{color:var(--ink2)}}
.med{{font-family:var(--mono);font-size:10px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--ink3);margin-top:4px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
.dot{{width:7px;height:7px;border-radius:50%;flex:0 0 auto}}
.m-autograph .dot{{background:var(--m-autograph)}}
.m-manuscript .dot{{background:var(--m-manuscript)}}
.m-print .dot{{background:var(--m-print)}}
.prov{{font-size:9.5px;padding:1px 5px;border:1px solid var(--rule);border-radius:2px;
  letter-spacing:.05em}}
.prov.gal{{color:var(--m-autograph);border-color:currentColor}}
.prov.hand{{color:var(--m-manuscript);border-color:currentColor}}
.ttl{{font-size:14px;line-height:1.35;margin-top:7px;color:var(--ink)}}
.inst{{font-size:12.5px;color:var(--ink2);margin-top:2px;line-height:1.35}}
.have{{font-family:var(--mono);font-size:10.5px;color:var(--ink3);margin-top:6px;
  letter-spacing:.03em}}
dl{{margin:7px 0 0;display:grid;grid-template-columns:auto 1fr;gap:1px 9px;
  font-size:11.5px;line-height:1.45}}
dt{{font-family:var(--mono);font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink3);padding-top:2px}}
dd{{margin:0;color:var(--ink2)}}
.go{{margin-top:9px;font-family:var(--mono);font-size:10.5px;letter-spacing:.03em}}
.path{{color:var(--ink3);word-break:break-all}}
.path a{{color:inherit;text-decoration:none;border-bottom:1px dotted currentColor}}
.path a:hover{{color:var(--ink)}}

.colo{{margin-top:56px;border-top:1px solid var(--ink);padding-top:20px;
  font-size:13.5px;color:var(--ink3);max-width:70ch;line-height:1.6}}
.colo code{{font-family:var(--mono);font-size:12px;color:var(--ink2);background:var(--sunk);
  padding:1px 5px}}
.empty{{font-family:var(--mono);font-size:12px;color:var(--ink3);padding:26px 0}}
@media (max-width:520px){{
  .grid{{grid-template-columns:1fr}}
  .tally{{margin-left:0;width:100%}}
}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
/* Keep the flex sizing the anchor had -- a <button> defaults differently, and an earlier
   `width:100%` here made the thumbnail claim the whole card and squeeze the text to one
   character per line. */
.shot{{flex:0 0 auto;align-self:flex-start;display:block;width:auto;line-height:0;
  padding:0;border:0;background:none;cursor:zoom-in;position:relative;
  font:inherit;color:inherit;text-align:left}}
.shot:focus-visible{{outline:2px solid var(--ink);outline-offset:2px}}
.shot::after{{content:'';position:absolute;inset:0;box-shadow:inset 0 0 0 2px transparent;
  transition:box-shadow .12s}}
.item:hover .shot::after{{box-shadow:inset 0 0 0 2px rgba(0,0,0,.28)}}
#zoom{{position:fixed;inset:0;z-index:50;display:none;place-items:center;
  background:rgba(12,12,14,.86);padding:2rem;cursor:zoom-out}}
#zoom.on{{display:grid}}
#zoom img{{max-width:min(94vw,860px);max-height:86vh;width:auto;height:auto;
  box-shadow:0 18px 60px rgba(0,0,0,.6);background:#fff}}
#zoom figcaption{{margin-top:.7rem;color:#e9e6e0;text-align:center;
  font:500 .76rem/1.4 'IBM Plex Mono',monospace}}
@media (hover:none){{.pgnote{{opacity:1}}}}
.sig{{cursor:help;border-bottom:1px dotted rgba(0,0,0,.3)}}
.sig.plain{{cursor:auto;border-bottom:0}}
.none{{color:var(--faint)}}
.tier{{display:inline-block;min-width:1.05rem;text-align:center;border-radius:2px;
  font:600 .64rem/1.35 'IBM Plex Mono',monospace;padding:0 .18rem;color:#fff;background:#999}}
.tier.tA{{background:#2f6d3f}} .tier.tB{{background:#3c6f8c}} .tier.tC{{background:#8a7a44}}
.tier.tD{{background:#9a6a3a}} .tier.tE{{background:#a33}} .tier.tF{{background:#777}}
.tlab{{color:var(--ink2)}}
dd a{{margin-right:.3rem}}
.path{{margin:.42rem 0 0;font:500 .62rem/1.3 'IBM Plex Mono',monospace;color:var(--faint);
  word-break:break-all}}
.opindex{{display:flex;flex-wrap:wrap;gap:.4rem;margin:0 0 1.1rem}}
.opindex a{{display:flex;align-items:baseline;gap:.4rem;padding:.3rem .6rem;
  border:1px solid var(--rule);border-radius:2px;text-decoration:none;color:var(--ink);
  font:500 .8rem/1 'IBM Plex Mono',monospace;background:var(--card)}}
.opindex a:hover{{border-color:var(--ink)}}
.opindex a b{{font-weight:600;opacity:.55;font-size:.72rem}}
@media (max-width:640px){{.opindex a{{padding:.26rem .45rem;font-size:.72rem}}}}
</style>

<div class="wrap">
<header class="mast">
  <h1>The Boccherini facsimile shelf</h1>
  <p class="lede">Every scan of a Boccherini string quartet now on disk —
    <b>{len(its)} sources</b> from <b>{len(libs)} libraries</b>, {n_img:,} page images and
    {n_pdf} part PDFs, {size_gb:.1f} GB. Colour is the medium: iron-gall brown for an
    <b>autograph</b>, indigo for a <b>manuscript copy</b>, graphite for an early
    <b>print</b>. Click any page to open the scan at its library.</p>
  <div class="tiles">
    <div class="tile"><b>{len(its)}</b><span>sources held</span></div>
    <div class="tile a"><b>{len(auto)}</b><span>autograph</span></div>
    <div class="tile m"><b>{len(ms)}</b><span>manuscript copies</span></div>
    <div class="tile p"><b>{len(pr)}</b><span>early prints</span></div>
    <div class="tile"><b>{n_img:,}</b><span>page images</span></div>
  </div>
</header>

<figure id="zoom" aria-hidden="true"><img alt=""><figcaption></figcaption></figure>
<nav class="opindex" aria-label="Jump to an opus">
  {''.join(f'<a href="#{i}">{e(lbl)}<b>{n}</b></a>' for i, lbl, n in nav)}
</nav>
<div class="controls">
  <input type="search" id="q" placeholder="siglum, shelfmark, library, title, folder…" aria-label="Filter sources">
  <button class="chip" id="f-autograph" aria-pressed="false">autograph</button>
  <button class="chip" id="f-manuscript" aria-pressed="false">manuscript</button>
  <button class="chip" id="f-print" aria-pressed="false">print</button>
  <button class="chip" id="f-unchecked" aria-pressed="false" title="asserted, disagreeing, or unsupported">needs checking</button>
  <span class="tally" id="tally"></span>
</div>


{''.join(sec)}
<p class="empty" id="none" hidden>Nothing matches that filter.</p>

<footer class="colo">
  <p>Built by <code>build_sources_page.py</code> from the files under
  <code>digitizations/</code>. Sources marked <em>linked by RISM</em> came from MARC 856 via
  <code>rism_digitizations.py</code>; those marked <em>found on Gallica</em> came from
  <code>find_scans.py</code>, which searches the BnF for the 95% of holdings RISM links no
  scan for. Opus rows and the Gérard spine follow
  <a href="https://quartets.boccherini.org/" target="_blank" rel="noopener">quartets.boccherini.org</a>,
  the same layout as the companion incipit table. Medium is RISM's MARC 593 where RISM has a
  record, and a reading of Gallica's own title where it does not — so a Gallica
  <em>autograph</em> is Gallica's claim, not an independent one.</p>
</footer>
</div>

<script>
(function(){{
  var items=[].slice.call(document.querySelectorAll('.item')),
      secs=[].slice.call(document.querySelectorAll('.opus')),
      q=document.getElementById('q'), tally=document.getElementById('tally'),
      none=document.getElementById('none'),
      keys=['autograph','manuscript','print','unchecked'],
      on={{}};
  keys.forEach(function(k){{
    var b=document.getElementById('f-'+k);
    b.addEventListener('click',function(){{
      on[k]=!on[k]; b.setAttribute('aria-pressed',on[k]?'true':'false'); apply();
    }});
  }});
  function apply(){{
    var term=(q.value||'').trim().toLowerCase(),
        meds=keys.slice(0,3).filter(function(k){{return on[k];}}),
        shown=0;
    items.forEach(function(el){{
      var ok=true;
      // An autograph is a manuscript. Filtering 'manuscript' and getting only the
      // non-autograph ones is not what anyone means by it.
      var med=el.dataset.medium,
          hit=meds.indexOf(med)>=0 || (meds.indexOf('manuscript')>=0 && med==='autograph');
      if(meds.length && !hit) ok=false;
      // 'needs checking' is D, E or F -- asserted, contradicted, or unsupported.
      if(ok && on.unchecked && 'DEF'.indexOf(el.dataset.tier)<0) ok=false;
      if(ok && term && el.dataset.q.indexOf(term)<0) ok=false;
      el.hidden=!ok; if(ok) shown++;
    }});
    secs.forEach(function(s){{
      s.hidden=!s.querySelector('.item:not([hidden])');
    }});
    none.hidden=shown>0;
    tally.textContent=shown+' of '+items.length+' sources';
  }}
  q.addEventListener('input',apply);
  apply();

  // Enlargement. Hover previews on a pointer device, tap/click on anything; Escape or a
  // click anywhere closes. The big image is already in the page, so it is instant.
  var zoom=document.getElementById('zoom'),zi=zoom.querySelector('img'),
      zc=zoom.querySelector('figcaption'),hoverOK=matchMedia('(hover:hover)').matches,timer;
  function show(btn){{
    var big=btn.getAttribute('data-big'); if(!big) return;
    zi.src=big; zc.textContent=btn.getAttribute('data-cap')||'';
    zoom.classList.add('on'); zoom.setAttribute('aria-hidden','false');
  }}
  function hide(){{
    zoom.classList.remove('on'); zoom.setAttribute('aria-hidden','true'); zi.removeAttribute('src');
  }}
  document.querySelectorAll('.shot').forEach(function(btn){{
    btn.addEventListener('click',function(ev){{ ev.preventDefault(); show(btn); }});
    if(hoverOK){{
      btn.addEventListener('mouseenter',function(){{ timer=setTimeout(function(){{show(btn);}},260); }});
      btn.addEventListener('mouseleave',function(){{ clearTimeout(timer); }});
    }}
  }});
  zoom.addEventListener('click',hide);
  document.addEventListener('keydown',function(ev){{ if(ev.key==='Escape') hide(); }});
}})();
</script>'''

    OUT.write_text(page)
    print(f'{OUT} — {len(page)/1e6:.2f} MB, {len(its)} items '
          f'({len(auto)} autograph, {len(ms)} ms, {len(pr)} print)', file=sys.stderr)


if __name__ == '__main__':
    main()
