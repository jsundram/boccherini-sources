# /// script
# requires-python = ">=3.11"
# dependencies = ["verovio"]
# ///
"""Engrave the RISM incipits onto the Periodic Table layout.

    uv run tools/build_page.py                      # -> boccherini_incipits.html

Layout, opus rows and the G-number spine come from quartets.boccherini.org
(`opera.json`, vendored beside this script). RISM incipits are joined on the
Gerard number, and each card's movement bar is filled where RISM has an incipit
for that movement -- so an empty bar is a real gap against a known movement
count, not just an absence of data.

Plaine & Easie is what RISM stores (MARC 031 $g/$n/$o/$p). Verovio -- the same
engraver rism.online uses -- reads it directly, so no LilyPond round-trip is
needed. Verovio exports MEI, Humdrum and MIDI; it does NOT export MusicXML.
"""
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import verovio

CACHE = Path('.rism-cache')
SRC = Path('boccherini-rism-incipits.jsonl')
OPERA = Path('opera.json')
OUT = Path('boccherini_incipits.html')
M = '{http://www.loc.gov/MARC21/slim}'
BIRTH = 1743
UNNUM = 'unnumbered'

# Row packing, as quartets.boccherini.org does it: small opera share a row.
EXCLUDE_FROM_COMBINING = {64}
MAX_PER_ROW = 4
MAX_TO_COMBINE = 2


# ---------------------------------------------------------------- engraving

GLYPH_DEF = re.compile(r'<g id="(E[0-9A-F]+)-[^"]*">(.*?)</g>', re.S)


def engraver():
    tk = verovio.toolkit()
    tk.setOptions({
        'inputFrom': 'pae', 'adjustPageHeight': True, 'adjustPageWidth': True,
        'scale': 28, 'header': 'none', 'footer': 'none', 'breaks': 'none',
        'pageMarginTop': 0, 'pageMarginBottom': 0, 'pageMarginLeft': 0,
        'pageMarginRight': 0, 'svgViewBox': True, 'svgRemoveXlink': True,
        'svgFormatRaw': True, 'xmlIdSeed': 1,
    })
    return tk


def engrave(tk, pae, glyphs):
    """Render one incipit, hoisting its glyph <defs> into the shared sprite.

    Verovio repeats every notehead/clef path in every SVG and scopes its <style>
    to a per-render id; pulling both out drops each staff from ~15KB to ~6KB."""
    if not tk.loadData(pae):
        return None
    svg = tk.renderToSVG(1)
    d = re.search(r'<defs>.*?</defs>', svg, re.S)
    if d:
        for g in GLYPH_DEF.finditer(d[0]):
            glyphs.setdefault(g[1], g[2])
        svg = svg.replace(d[0], '')
    svg = re.sub(r'href="#(E[0-9A-F]+)-[^"]*"', r'href="#\1"', svg)   # -> shared sprite
    svg = re.sub(r'<style.*?</style>', '', svg, flags=re.S)           # -> page CSS
    svg = re.sub(r'<desc>.*?</desc>', '', svg, flags=re.S)
    svg = re.sub(r'\sid="[^"]*"', '', svg)
    return svg


# ---------------------------------------------------------------- RISM side

def rism_by_gerard():
    """{gerard -> {movement -> {pae -> reading}}} plus per-work source ids."""
    works = defaultdict(lambda: {'mvts': defaultdict(dict), 'sources': set()})
    for line in SRC.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        sid = r['source'].rsplit('/', 1)[1]
        # RISM leaves a few sources without a GerB number; keep them, unplaceable.
        w = works[r['gerard'] or UNNUM]
        w['sources'].add(sid)
        parts = r['mvt'].split('.')
        mv = parts[1] if len(parts) > 2 and parts[1] else '?'
        rd = w['mvts'][mv].setdefault(r['pae'], {'caption': r['caption'], 'part': r['part'], 'srcs': []})
        rd['srcs'].append({'sid': sid, 'siglum': r['siglum']})
        if not rd['caption']:
            rd['caption'] = r['caption']
    return works


# ---------------------------------------------------------------- key signatures

CIRCLE = {  # name -> (count, sign); from the site's circle-of-fifths table
    'C major': (0, ''), 'A minor': (0, ''),
    'G major': (1, '♯'), 'E minor': (1, '♯'),
    'D major': (2, '♯'), 'B minor': (2, '♯'),
    'A major': (3, '♯'), 'F-sharp minor': (3, '♯'),
    'E major': (4, '♯'), 'C-sharp minor': (4, '♯'),
    'B major': (5, '♯'), 'G-sharp minor': (5, '♯'),
    'F major': (1, '♭'), 'D minor': (1, '♭'),
    'B-flat major': (2, '♭'), 'G minor': (2, '♭'),
    'E-flat major': (3, '♭'), 'C minor': (3, '♭'),
    'A-flat major': (4, '♭'), 'F minor': (4, '♭'),
    'D-flat major': (5, '♭'), 'B-flat minor': (5, '♭'),
}


def keysig(q):
    return CIRCLE.get(f"{q['key']} {'major' if q['major'] else 'minor'}", (0, ''))


# ---------------------------------------------------------------- cards

def coverage(q, w):
    """Which of this quartet's real movements RISM has an incipit for."""
    n = len(q['mvmts'])
    have = {int(m) for m in (w['mvts'] if w else {}) if m.isdigit()}
    return [i + 1 in have for i in range(n)], have


def card(q, opus, works, ids):
    g = str(q['gerard'])
    w = works.get(g)
    bars, have = coverage(q, w)
    n = len(q['mvmts'])
    got = sum(bars)
    cnt, sign = keysig(q)
    minuet = any('Minuetto' in m for m in q['mvmts'])

    state = 'none' if got == 0 else ('full' if got >= n else 'partial')
    accid = ''.join(f'<span>{sign}</span>' for _ in range(cnt))
    barsvg = ''.join(
        f'<i class="mb{" on" if on else ""}" title="Mvt {i + 1}: {html.escape(q["mvmts"][i])}'
        f'{" — incipit in RISM" if on else " — no incipit"}"></i>'
        for i, on in enumerate(bars))

    tip = {
        'g': g, 'opus': opus['opus'], 'n': q.get('number'),
        'key': f"{q['key'].replace('-flat', chr(0x266d)).replace('-sharp', chr(0x266f))} "
               f"{'major' if q['major'] else 'minor'}",
        'mv': q['mvmts'], 'have': sorted(have),
        'srcs': len(w['sources']) if w else 0,
    }
    href = f'#g{g}' if got else ''
    tag = 'a' if got else 'div'
    return (
        f'<{tag} class="quartet-card cov-{state}{"" if minuet else " no-minuet"}"'
        f'{f" href={chr(34)}{href}{chr(34)}" if got else ""}'
        f' data-tip="{html.escape(json.dumps(tip), quote=True)}">'
        f'<div class="mode-bar {"major" if q["major"] else "minor"}">'
        f'<div class="gerard-number">{g}</div>'
        f'<div class="quartet-number">{f"#{q['number']}" if q.get('number') else ''}</div></div>'
        f'<div class="card-content"><div class="key-section">'
        f'<div class="key-signature">{html.escape(q["key"].replace("-flat", chr(0x266d)).replace("-sharp", chr(0x266f)))}</div>'
        f'<div class="key-mode">{"major" if q["major"] else "minor"}</div></div></div>'
        f'{f"<div class=key-accidentals>{accid}</div>" if cnt else ""}'
        f'<div class="cov-strip cov-{state}">'
        f'<span class="cov-n">{got}/{n}</span><span class="mvmt-bars">{barsvg}</span></div>'
        f'</{tag}>')


def opus_label(opus):
    cat = opus['quartets'][0]['category'] if opus['quartets'] else 'opera grande'
    grande = 'grande' in cat
    imslp = (f'<a class="imslp-link" href="{opus["imslp"]}" target="_blank" rel="noopener">imslp</a>'
             if opus.get('imslp') else '')
    ded = (f'<div class="dedication">{html.escape(opus["dedication"])}</div>'
           if opus.get('dedication') else '')
    return (
        f'<div class="opus-label {"grande-bg" if grande else "piccola-bg"}">'
        f'<div class="year-age"><span class="year">{opus["year"]}</span>'
        f'<span class="age">({opus["year"] - BIRTH})</span></div>{ded}'
        f'<div class="opus-number">{opus["opus"]}</div>'
        f'<div class="bottom-section">{imslp}'
        f'<div class="category-badge {"grande" if grande else "piccola"}">'
        f'{"Grande" if grande else "Piccola"}</div></div></div>')


def rows(opera, works, ids):
    """Pack opus rows exactly as the site does: small opera share a row."""
    out, pending, count = [], [], 0

    def flush():
        nonlocal pending, count
        if pending:
            out.append(render_row(pending, works, ids))
            pending, count = [], 0

    for opus in opera:
        n = len(opus['quartets'])
        if opus['opus'] in EXCLUDE_FROM_COMBINING or n > MAX_TO_COMBINE:
            flush()
            out.append(render_row([opus], works, ids))
        else:
            if count + n > MAX_PER_ROW:
                flush()
            pending.append(opus)
            count += n
    flush()
    return ''.join(out)


def render_row(opuses, works, ids):
    parts = []
    for i, opus in enumerate(opuses):
        parts.append(opus_label(opus))
        parts.append('<div class="quartets-container">' +
                     ''.join(card(q, opus, works, ids) for q in opus['quartets']) +
                     '</div>')
        if i < len(opuses) - 1:
            parts.append('<div class="opus-spacer"></div>')
    cls = 'opus-row combined-pair' if len(opuses) > 1 else 'opus-row'
    return f'<div class="{cls}">{"".join(parts)}</div>'


# ---------------------------------------------------------------- catalogue

def catalogue(opera, works, tk, glyphs):
    """Engraved incipits, grouped by Gerard number then movement."""
    index = {}
    for o in opera:
        for q in o['quartets']:
            index[str(q['gerard'])] = (o, q)

    secs = []
    for g in sorted(works, key=lambda x: (int(re.match(r'(\d+)', x)[1]) if re.match(r'\d', x) else 10 ** 9, x)):
        w = works[g]
        o, q = index.get(g, (None, None))
        bars, _ = coverage(q, w) if q else ([], set())
        n = len(q['mvmts']) if q else len(w['mvts'])
        got = sum(bars) if q else len([m for m in w['mvts'] if m != '?'])

        trs = []
        for mv in sorted(w['mvts'], key=lambda x: (x == '?', int(x) if x.isdigit() else 0)):
            reads = list(w['mvts'][mv].items())
            name = (q['mvmts'][int(mv) - 1] if q and mv.isdigit() and int(mv) <= len(q['mvmts']) else None)
            for i, (pae, rd) in enumerate(reads):
                svg = engrave(tk, pae, glyphs) or '<span class="nope">Plaine &amp; Easie did not parse</span>'
                head = (f'<th class="mv" rowspan="{len(reads)}" scope="rowgroup">'
                        f'<span class="mvn">{html.escape(mv)}</span>'
                        f'{f"<span class=mvname>{html.escape(name)}</span>" if name else ""}</th>'
                        ) if i == 0 else ''
                sigla = sorted({s['siglum'] for s in rd['srcs'] if s['siglum']})
                links = ' '.join(
                    f'<a class="src" href="https://rism.online/sources/{s["sid"]}" target="_blank" rel="noopener">{s["sid"]}</a>'
                    for s in rd['srcs'])
                trs.append(
                    f'<tr>{head}'
                    f'<td class="notation"><div class="staff">{svg}</div>'
                    f'<details class="pae"><summary>Plaine &amp; Easie</summary>'
                    f'<pre>{html.escape(pae)}</pre></details></td>'
                    f'<td class="cap"><b>{html.escape(rd["caption"] or "—")}</b>'
                    f'<span class="part">{html.escape(rd["part"] or "—")}</span></td>'
                    f'<td class="srcs"><span class="n">{len(rd["srcs"])} source'
                    f'{"s" if len(rd["srcs"]) != 1 else ""}</span>'
                    f'<span class="sig">{html.escape(", ".join(sigla[:6]))}{"…" if len(sigla) > 6 else ""}</span>'
                    f'<span class="ids">{links}</span></td></tr>')

        # movements the site knows about but RISM never indexed
        missing = ([i + 1 for i, on in enumerate(bars) if not on] if q else [])
        miss = ('<p class="missing">No incipit in RISM for ' +
                ', '.join(f'<b>{i}. {html.escape(q["mvmts"][i - 1])}</b>' for i in missing) +
                '</p>') if missing else ''

        title = f'G {g}' if re.match(r'\d', g) else ('Unnumbered' if g == UNNUM else f'G {g}')
        sub = (f'Op. {o["opus"]}{f" no. {q['number']}" if q.get('number') else ''} · '
               f'{html.escape(q["key"].replace("-flat", chr(0x266d)).replace("-sharp", chr(0x266f)))} '
               f'{"major" if q["major"] else "minor"} · {o["year"]}') if q else 'not in the Periodic Table'
        secs.append(
            f'<section class="work" id="g{g}" data-search="{html.escape((g + " " + (f"op. {o['opus']}" if o else "") + " " + " ".join(q["mvmts"] if q else [])).lower())}" data-cov="{got}" data-n="{n}">'
            f'<header class="work-hd"><h3>{title}</h3><span class="wsub">{sub}</span>'
            f'<span class="wcov">{got} of {n} movements</span></header>'
            f'{miss}'
            f'<table class="mvts"><thead><tr><th>Mvt</th><th>Incipit</th>'
            f'<th>Tempo &amp; part</th><th>Transmitted by</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></section>')
    return ''.join(secs)


# ---------------------------------------------------------------- page

def render():
    opera = json.loads(OPERA.read_text())
    works = rism_by_gerard()
    tk, glyphs = engraver(), {}

    ids = {str(q['gerard']) for o in opera for q in o['quartets']}
    table = rows(opera, works, ids)
    cat = catalogue(opera, works, tk, glyphs)

    quartets = [q for o in opera for q in o['quartets']]
    tot_mv = sum(len(q['mvmts']) for q in quartets)
    have_mv = sum(sum(coverage(q, works.get(str(q['gerard'])))[0]) for q in quartets)
    with_any = sum(1 for q in quartets if sum(coverage(q, works.get(str(q['gerard'])))[0]))
    complete = sum(1 for q in quartets
                   if sum(coverage(q, works.get(str(q['gerard'])))[0]) == len(q['mvmts']))
    n_inc = sum(len(rd['srcs']) for w in works.values() for m in w['mvts'].values() for rd in m.values())
    orphan = sorted(set(works) - ids, key=lambda x: int(re.match(r'(\d+)', x)[1]) if re.match(r'\d', x) else 10 ** 9)

    sprite = ''.join(f'<g id="{k}">{v}</g>' for k, v in sorted(glyphs.items()))
    stats = [
        (f'{have_mv}/{tot_mv}', 'movements engraved', 'of all 91 quartets'),
        (complete, 'quartets complete', 'every movement has an incipit'),
        (len(quartets) - with_any, 'quartets absent', 'no incipit in RISM at all'),
        (n_inc, 'incipits', f'across {len({s for w in works.values() for s in w["sources"]})} sources'),
    ]
    return PAGE.format(
        sprite=sprite, table=table, works=cat,
        stats=''.join(f'<div class="stat"><b>{n}</b><span>{l}</span><i>{s}</i></div>' for n, l, s in stats),
        have=have_mv, tot=tot_mv, absent=len(quartets) - with_any,
        orphan=', '.join(f'G&nbsp;{o}' if re.match(r'\d', o) else o for o in orphan))


PAGE = '''<title>Boccherini Incipit Table</title>
<style>
:root{{
  --card-height:clamp(100px,12vw,140px); --card-gap:clamp(6px,0.8vw,10px);
  --opus-label-width:clamp(85px,8vw,95px);
  --top-section-height:clamp(14px,1.7vw,20px);
  --nickname-height:clamp(10px,1.3vw,15px);
  --bottom-section-height:clamp(16px,2vw,22px);
  --middle-section-height:calc(var(--card-height) - var(--top-section-height) - var(--nickname-height) - var(--bottom-section-height));
  --top-font-size:0.8em; --middle-font-size:2.8em; --bottom-font-size:0.7em;

  --bg-body:#f5f5f5; --bg-card:#fff; --bg-card-no-minuet:rgba(0,0,0,.03);
  --bg-tooltip:rgba(0,0,0,.9); --text-on-tooltip:#fff;
  --bg-mode-bar-major:transparent; --bg-mode-bar-minor:#E91E63;
  --text-primary:#222; --text-secondary:#333; --text-tertiary:#444;
  --text-muted:#666; --text-light:#777; --text-lighter:#888; --text-lightest:#999;
  --text-link:#2196F3; --text-link-hover:#1976D2;
  --text-gerard-major:#444; --text-quartet-major:#888;
  --text-gerard-minor:#fff; --text-quartet-minor:rgba(255,255,255,.85);
  --border-card:#ddd; --border-card-hover:#888; --border-card-active:#333;
  --shadow-card:rgba(0,0,0,.1); --shadow-card-hover:rgba(0,0,0,.2);
  --badge-grande-bg:#81C784; --badge-grande-text:#333;
  --badge-piccola-bg:#CE93D8; --badge-piccola-text:#333;
  --gradient-grande:rgba(129,199,132,.12); --gradient-piccola:rgba(206,147,216,.12);
  --rule:#e0e0e0; --panel:#ececec;
  /* coverage encoding: one hue, light -> dark */
  --cov-full:#2E7D32; --cov-partial:#F9A825; --cov-none:#B0BEC5;
  --bar-on:#2E7D32; --bar-off:#cfcfcf; --staff:#222;
}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg-body:#1a1a1a; --bg-card:#2d2d2d; --bg-card-no-minuet:rgba(255,255,255,.03);
  --bg-tooltip:rgba(240,240,240,.95); --text-on-tooltip:#111;
  --text-primary:#f0f0f0; --text-secondary:#e0e0e0; --text-tertiary:#d0d0d0;
  --text-muted:#aaa; --text-light:#999; --text-lighter:#888; --text-lightest:#777;
  --text-link:#64B5F6; --text-link-hover:#90CAF9;
  --text-gerard-major:#d0d0d0; --text-quartet-major:#888;
  --border-card:#444; --border-card-hover:#777; --border-card-active:#aaa;
  --shadow-card:rgba(0,0,0,.4); --shadow-card-hover:rgba(0,0,0,.6);
  --gradient-grande:rgba(129,199,132,.10); --gradient-piccola:rgba(206,147,216,.10);
  --rule:#3a3a3a; --panel:#242424;
  --cov-full:#66BB6A; --cov-partial:#FFCA28; --cov-none:#546E7A;
  --bar-on:#66BB6A; --bar-off:#4a4a4a; --staff:#f0f0f0;
}}}}
:root[data-theme="dark"]{{
  --bg-body:#1a1a1a; --bg-card:#2d2d2d; --bg-card-no-minuet:rgba(255,255,255,.03);
  --bg-tooltip:rgba(240,240,240,.95); --text-on-tooltip:#111;
  --text-primary:#f0f0f0; --text-secondary:#e0e0e0; --text-tertiary:#d0d0d0;
  --text-muted:#aaa; --text-light:#999; --text-lighter:#888; --text-lightest:#777;
  --text-link:#64B5F6; --text-link-hover:#90CAF9;
  --text-gerard-major:#d0d0d0; --text-quartet-major:#888;
  --border-card:#444; --border-card-hover:#777; --border-card-active:#aaa;
  --shadow-card:rgba(0,0,0,.4); --shadow-card-hover:rgba(0,0,0,.6);
  --gradient-grande:rgba(129,199,132,.10); --gradient-piccola:rgba(206,147,216,.10);
  --rule:#3a3a3a; --panel:#242424;
  --cov-full:#66BB6A; --cov-partial:#FFCA28; --cov-none:#546E7A;
  --bar-on:#66BB6A; --bar-off:#4a4a4a; --staff:#f0f0f0;
}}
*{{box-sizing:border-box}}
body{{font-family:'Helvetica Neue',Arial,sans-serif;background:var(--bg-body);
  color:var(--text-primary);margin:0;padding:0}}
.page{{padding-inline:16px;padding-block:24px 64px}}
.container{{width:fit-content;max-width:100%;margin:0 auto;display:flex;flex-direction:column}}

/* ---------- masthead ---------- */
.mast{{max-width:1000px;margin:0 auto 26px}}
h1{{margin:0 0 6px;font-size:clamp(26px,4.2vw,44px);font-weight:800;letter-spacing:-.02em;
  color:var(--text-secondary);text-wrap:balance}}
.subtitle{{margin:0 0 18px;color:var(--text-muted);font-style:italic;
  font-size:clamp(14px,1.3vw,16px);max-width:70ch;line-height:1.5}}
.subtitle a{{color:var(--text-link);text-decoration:none}}
.subtitle a:hover{{text-decoration:underline}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1px;
  background:var(--rule);border:1px solid var(--rule);margin-bottom:8px}}
.stat{{background:var(--bg-body);padding:12px 14px;display:flex;flex-direction:column;gap:2px}}
.stat b{{font-size:26px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums}}
.stat span{{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}}
.stat i{{font-style:normal;font-size:12px;color:var(--text-lightest)}}

/* ---------- periodic table (layout from quartets.boccherini.org) ---------- */
.opus-row{{display:flex;align-items:flex-start;margin-bottom:10px}}
.opus-label{{width:var(--opus-label-width);height:var(--card-height);
  padding:clamp(1px,.2vw,2px) clamp(3px,.5vw,6px) 0 clamp(5px,.8vw,10px);
  display:flex;flex-direction:column;justify-content:flex-start;text-align:right;position:relative;
  flex-shrink:0}}
.opus-label.grande-bg{{background:linear-gradient(to right,transparent 0,var(--gradient-grande) 100%)}}
.opus-label.piccola-bg{{background:linear-gradient(to right,transparent 0,var(--gradient-piccola) 100%)}}
.opus-label .year-age{{display:flex;justify-content:space-between;align-items:center;
  height:var(--top-section-height);flex-shrink:0;line-height:1}}
.opus-label .year{{font-size:var(--top-font-size);font-weight:700;color:var(--text-tertiary);line-height:1}}
.opus-label .age{{font-size:calc(var(--top-font-size)*.85);color:var(--text-light);line-height:1}}
.opus-label .opus-number{{font-size:var(--middle-font-size);font-weight:900;color:var(--text-primary);
  line-height:1;letter-spacing:-.03em;height:var(--middle-section-height);
  margin-bottom:var(--nickname-height);flex-shrink:0;display:flex;align-items:center;justify-content:flex-end}}
.opus-label .bottom-section{{display:flex;flex-direction:column;align-items:flex-end;
  justify-content:center;flex-shrink:0;height:var(--bottom-section-height);position:relative}}
.opus-label .dedication{{position:absolute;top:calc(var(--top-section-height) + 2px);left:0;right:0;
  font-size:.6em;font-style:italic;color:var(--text-lightest);text-align:center;line-height:1.2;z-index:1}}
.opus-label .category-badge{{font-size:var(--bottom-font-size);width:100%;height:100%;
  display:flex;align-items:center;justify-content:center;font-weight:500;line-height:1}}
.category-badge.grande{{background:var(--badge-grande-bg);color:var(--badge-grande-text)}}
.category-badge.piccola{{background:var(--badge-piccola-bg);color:var(--badge-piccola-text)}}
.opus-label .imslp-link{{position:absolute;bottom:100%;left:0;margin-bottom:1px;padding:2px 4px;
  font-size:.65em;font-weight:400}}
.quartets-container{{display:flex;flex-wrap:nowrap;gap:var(--card-gap);margin-left:var(--card-gap)}}
.opus-spacer{{width:clamp(120px,15vw,177px);height:var(--card-height);flex-shrink:0;margin:0 var(--card-gap)}}

.quartet-card{{width:var(--card-height);height:var(--card-height);background:var(--bg-card);
  border:2px solid var(--border-card);border-radius:4px;padding:0;
  box-shadow:2px 2px 5px var(--shadow-card);cursor:pointer;transition:transform .2s,box-shadow .2s,border-color .2s;
  position:relative;display:flex;flex-direction:column;overflow:hidden;flex-shrink:0;
  text-decoration:none;color:inherit}}
.quartet-card:hover,.quartet-card:focus-visible{{transform:translateY(-3px);
  box-shadow:3px 3px 10px var(--shadow-card-hover);border-color:var(--border-card-hover);outline:none}}
.quartet-card.no-minuet{{background:var(--bg-card-no-minuet)}}
.quartet-card.cov-none{{opacity:.55}}
.mode-bar{{height:var(--top-section-height);width:100%;flex-shrink:0;display:flex;
  justify-content:space-between;align-items:center;padding:0 8px}}
.mode-bar.major{{background:var(--bg-mode-bar-major)}}
.mode-bar.minor{{background:var(--bg-mode-bar-minor)}}
.mode-bar.major .gerard-number{{font-size:var(--top-font-size);font-weight:700;color:var(--text-gerard-major);line-height:1}}
.mode-bar.major .quartet-number{{font-size:var(--top-font-size);font-weight:600;color:var(--text-quartet-major);line-height:1}}
.mode-bar.minor .gerard-number{{font-size:var(--top-font-size);font-weight:700;color:var(--text-gerard-minor);line-height:1}}
.mode-bar.minor .quartet-number{{font-size:var(--top-font-size);font-weight:600;color:var(--text-quartet-minor);line-height:1}}
.card-content{{padding:0;flex:1;display:flex;flex-direction:column;min-height:0}}
.key-section{{height:var(--middle-section-height);margin-bottom:var(--nickname-height);flex-shrink:0;
  display:flex;flex-direction:column;justify-content:center;align-items:center;padding:0 8px}}
.key-signature{{font-size:calc(var(--middle-font-size)*.64);font-weight:700;color:var(--text-primary);line-height:1}}
.key-mode{{font-size:.75em;color:var(--text-muted);line-height:1;margin-top:2px}}
.key-accidentals{{position:absolute;left:3px;top:var(--top-section-height);display:flex;
  flex-direction:column;align-items:center;font-size:calc(var(--middle-section-height)/5);
  line-height:1.1;color:var(--text-lightest);opacity:.8;pointer-events:none}}
.key-accidentals span{{display:block}}

/* coverage strip replaces the site's movement-count strip */
.cov-strip{{height:var(--bottom-section-height);flex-shrink:0;display:flex;align-items:center;
  justify-content:center;gap:6px;line-height:1;font-size:var(--bottom-font-size);font-weight:600}}
.cov-strip.cov-full{{background:var(--cov-full);color:#fff}}
.cov-strip.cov-partial{{background:var(--cov-partial);color:#3a2d00}}
.cov-strip.cov-none{{background:var(--cov-none);color:#1f2a2e}}
.cov-n{{font-variant-numeric:tabular-nums;opacity:.95}}
.mvmt-bars{{display:flex;gap:3px}}
.mb{{width:11px;height:9px;border-radius:2px;background:rgba(255,255,255,.35);
  border:1px solid rgba(0,0,0,.25);display:block}}
.mb.on{{background:#fff;border-color:rgba(0,0,0,.35)}}
.cov-strip.cov-none .mb{{background:rgba(255,255,255,.25)}}

.tooltip{{position:absolute;top:0;left:0;background:var(--bg-tooltip);color:var(--text-on-tooltip);
  padding:10px 12px;border-radius:5px;font-size:13px;pointer-events:none;z-index:1000;
  max-width:300px;line-height:1.45;opacity:0;transition:opacity .12s}}
.tooltip b{{display:block;margin-bottom:4px}}
.tooltip ol{{margin:6px 0 0;padding-left:18px}}
.tooltip li.no{{opacity:.5;text-decoration:line-through}}

.legend{{display:flex;flex-wrap:wrap;gap:10px 20px;align-items:center;margin:22px auto 0;
  padding:12px 14px;background:var(--panel);border:1px solid var(--rule);border-radius:4px;
  font-size:13px;color:var(--text-muted);max-width:1000px}}
.legend .k{{display:flex;align-items:center;gap:7px}}
.legend .sw{{width:26px;height:14px;border-radius:2px;display:inline-block}}
.note{{max-width:1000px;margin:16px auto 0;font-size:13.5px;color:var(--text-muted);
  border-left:3px solid var(--cov-partial);padding-left:12px;line-height:1.55}}

/* ---------- catalogue ---------- */
.cat{{max-width:1000px;margin:52px auto 0;border-top:2px solid var(--text-primary);padding-top:26px}}
h2{{font-size:clamp(20px,3vw,28px);font-weight:800;margin:0 0 6px}}
.lede{{color:var(--text-muted);margin:0 0 20px;max-width:68ch;line-height:1.55}}
.controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:18px;
  position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg-body);
  padding-block:10px;border-bottom:1px solid var(--rule)}}
input[type=search]{{font:inherit;font-size:15px;padding:8px 12px;border:1px solid var(--rule);
  border-radius:3px;background:var(--bg-card);color:var(--text-primary);flex:1 1 220px;min-width:0}}
input[type=search]:focus-visible{{outline:2px solid var(--text-link);outline-offset:1px}}
.toggle{{display:flex;align-items:center;gap:7px;font-size:14px;color:var(--text-muted);cursor:pointer}}
.count{{font-size:12px;color:var(--text-lightest);margin-left:auto;font-variant-numeric:tabular-nums}}

.work{{border-top:1px solid var(--rule);padding-block:20px}}
.work[hidden]{{display:none}}
.work-hd{{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 12px;margin-bottom:10px}}
.work-hd h3{{margin:0;font-size:21px;font-weight:800;letter-spacing:-.01em}}
.wsub{{color:var(--text-muted);font-size:14px}}
.wcov{{margin-left:auto;font-size:12px;color:var(--text-lightest);font-variant-numeric:tabular-nums}}
.missing{{margin:0 0 12px;font-size:13.5px;color:var(--text-muted);background:var(--panel);
  border-left:3px solid var(--cov-partial);padding:8px 12px;border-radius:0 3px 3px 0}}
.missing b{{color:var(--text-primary);font-weight:600}}

.mvts{{width:100%;border-collapse:collapse;font-size:14px}}
.mvts thead th{{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-lightest);
  text-align:left;padding:0 10px 7px;border-bottom:1px solid var(--rule);white-space:nowrap}}
.mvts td,.mvts th.mv{{border-bottom:1px solid var(--rule);padding:12px 10px;vertical-align:middle}}
.mvts tbody tr:last-child td,.mvts tbody tr:last-child th.mv{{border-bottom:0}}
th.mv{{width:130px;text-align:left;vertical-align:top;padding-top:16px}}
.mvn{{font-size:18px;font-weight:800;color:var(--cov-full);display:block}}
.mvname{{font-size:12px;color:var(--text-muted);display:block;margin-top:2px;font-weight:400}}
.notation{{width:46%}}
.staff{{color:var(--staff);overflow-x:auto;padding:2px 0}}
.staff svg{{height:44px;width:auto;max-width:none;display:block;fill:currentColor}}
.staff svg ellipse,.staff svg path,.staff svg polygon,.staff svg polyline,.staff svg rect{{stroke:currentColor}}
.staff svg g.dir,.staff svg g.dynam{{font-style:italic}}
.pae{{margin-top:6px}}
.pae summary{{font-size:10.5px;color:var(--text-lightest);cursor:pointer;letter-spacing:.06em;
  text-transform:uppercase;width:max-content}}
.pae summary:hover{{color:var(--text-link)}}
.pae pre{{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;white-space:pre-wrap;
  word-break:break-all;background:var(--panel);border:1px solid var(--rule);border-radius:3px;
  padding:9px 11px;margin:7px 0 0;color:var(--text-muted);user-select:all}}
.cap b{{font-weight:600;display:block}}
.cap .part{{font-size:11px;color:var(--text-lightest);display:block;margin-top:3px;
  font-family:ui-monospace,Menlo,monospace}}
.srcs{{width:180px}}
.srcs .n{{font-size:12.5px;font-weight:700;display:block}}
.srcs .sig{{font-size:11px;color:var(--text-muted);display:block;margin-top:3px;line-height:1.45;
  font-family:ui-monospace,Menlo,monospace}}
.srcs .ids{{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}}
a.src{{font-size:10px;color:var(--text-lightest);text-decoration:none;border:1px solid var(--rule);
  border-radius:2px;padding:1px 4px;font-family:ui-monospace,Menlo,monospace}}
a.src:hover{{color:var(--text-link);border-color:var(--text-link)}}
.nope{{font-size:13px;color:#E91E63;font-style:italic}}
.colophon{{max-width:1000px;margin:46px auto 0;padding-top:20px;border-top:2px solid var(--text-primary);
  font-size:13px;color:var(--text-lightest);line-height:1.6}}
.colophon code{{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--text-muted);
  background:var(--panel);padding:1px 5px;border-radius:2px}}
.colophon a{{color:var(--text-link)}}

.tablewrap{{overflow-x:auto;max-width:100%;padding-bottom:6px}}
@media (max-width:820px){{
  .notation{{width:auto}}
  .mvts,.mvts thead,.mvts tbody,.mvts tr,.mvts td,.mvts th.mv{{display:block;width:auto}}
  .mvts thead{{display:none}}
  .mvts td,.mvts th.mv{{border-bottom:0;padding:4px 0}}
  .mvts tbody tr{{border-bottom:1px solid var(--rule);padding-block:12px;display:block}}
  th.mv{{padding-top:0}}
  .srcs{{width:auto}} .wcov{{margin-left:0}}
}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style>

<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>{sprite}</defs></svg>

<div class="page">
  <div class="mast">
    <h1>Where RISM's Boccherini incipits stop</h1>
    <p class="subtitle">All 91 quartets on the layout of
      <a href="https://quartets.boccherini.org/" target="_blank" rel="noopener">quartets.boccherini.org</a>,
      with each card's bottom strip showing how many of its movements RISM actually
      indexed. <strong>{have} of {tot} movements</strong> have an incipit;
      <strong>{absent} quartets have none at all</strong>. Click any card to jump to its engraved staves.</p>
    <div class="stats">{stats}</div>
  </div>

  <div class="tablewrap"><div class="container">{table}</div></div>

  <div class="legend">
    <span class="k"><span class="sw" style="background:var(--cov-full)"></span> every movement indexed</span>
    <span class="k"><span class="sw" style="background:var(--cov-partial)"></span> some movements indexed</span>
    <span class="k"><span class="sw" style="background:var(--cov-none)"></span> nothing in RISM</span>
    <span class="k"><span class="mvmt-bars"><i class="mb on"></i><i class="mb"></i><i class="mb"></i></span> one slot per real movement, filled where an incipit exists</span>
  </div>
  <p class="note">The movement count comes from the Periodic Table, so an empty slot is a
  genuine gap in RISM against a movement we know exists &mdash; not merely missing data.
  Opus rows, years, keys, <em>opera grande / piccola</em> and the Gérard&nbsp;&rarr;&nbsp;opus
  mapping are all taken from <code>opera.json</code>. RISM also carries incipits for
  {orphan}, which the Periodic Table does not list as quartets; those appear in the catalogue below.</p>

  <div class="cat">
    <h2>The incipits</h2>
    <p class="lede">Grouped by Gérard number, then movement. Sources transmitting identical
    notes share a staff. Open <em>Plaine&nbsp;&amp;&nbsp;Easie</em> under any staff for the
    source code RISM stores.</p>
    <div class="controls">
      <input type="search" id="q" placeholder="Filter by G number, opus, or movement name…" aria-label="Filter works">
      <label class="toggle" for="gaps"><input type="checkbox" id="gaps"> Incomplete only</label>
      <span class="count" id="count"></span>
    </div>
    {works}
  </div>

  <p class="colophon">Incipits engraved with <a href="https://www.verovio.org" target="_blank" rel="noopener">Verovio</a>
  from the Plaine&nbsp;&amp;&nbsp;Easie in MARC&nbsp;031, harvested from
  <a href="https://rism.online" target="_blank" rel="noopener">RISM Online</a> by
  <code>rism_incipits.py</code> and built by <code>build_page.py</code>. Gérard numbers come from
  MARC&nbsp;690 (<code>GerB</code>, RISM <code>publications/29</code>). Layout, opus rows and the
  G&nbsp;&rarr;&nbsp;opus mapping from <code>opera.json</code> at quartets.boccherini.org.</p>
</div>

<script>
(function () {{
  var tip = document.createElement('div');
  tip.className = 'tooltip'; document.body.appendChild(tip);
  var touch = window.matchMedia('(hover:none) and (pointer:coarse)').matches, active = null;

  function show(card, x, y) {{
    var d; try {{ d = JSON.parse(card.dataset.tip); }} catch (e) {{ return; }}
    var have = {{}}; d.have.forEach(function (m) {{ have[m] = 1; }});
    var li = d.mv.map(function (m, i) {{
      return '<li class="' + (have[i + 1] ? 'yes' : 'no') + '">' + m + '</li>';
    }}).join('');
    tip.innerHTML = '<b>Op. ' + d.opus + (d.n ? ' no. ' + d.n : '') + ' in ' + d.key +
      ', G. ' + d.g + '</b>' +
      (d.srcs ? d.srcs + ' RISM source' + (d.srcs === 1 ? '' : 's') : 'not in RISM') +
      '<ol>' + li + '</ol>';
    var w = 300, left = Math.min(x + 12, window.scrollX + document.documentElement.clientWidth - w - 8);
    tip.style.left = Math.max(window.scrollX + 8, left) + 'px';
    tip.style.top = (y + 14) + 'px';
    tip.style.opacity = 1;
    active = card;
  }}
  function hide() {{ tip.style.opacity = 0; active = null; }}

  document.querySelectorAll('.quartet-card').forEach(function (c) {{
    if (touch) {{
      c.addEventListener('click', function (e) {{
        if (active === c) {{ hide(); return; }}
        e.preventDefault();
        show(c, e.pageX || 0, e.pageY || 0);
      }});
    }} else {{
      c.addEventListener('mouseenter', function (e) {{ show(c, e.pageX, e.pageY); }});
      c.addEventListener('mousemove', function (e) {{ if (active === c) show(c, e.pageX, e.pageY); }});
      c.addEventListener('mouseleave', hide);
      c.addEventListener('focus', function () {{
        var r = c.getBoundingClientRect();
        show(c, r.left + window.scrollX, r.bottom + window.scrollY);
      }});
      c.addEventListener('blur', hide);
    }}
  }});
  if (touch) document.body.addEventListener('click', function (e) {{
    if (!e.target.closest('.quartet-card')) hide();
  }});

  var q = document.getElementById('q'), gaps = document.getElementById('gaps'),
      count = document.getElementById('count'),
      works = [].slice.call(document.querySelectorAll('.work'));
  function apply() {{
    var t = q.value.trim().toLowerCase(), only = gaps.checked, n = 0;
    works.forEach(function (w) {{
      var ok = (!t || w.dataset.search.indexOf(t) > -1) &&
               (!only || w.dataset.cov !== w.dataset.n);
      w.hidden = !ok; if (ok) n++;
    }});
    count.textContent = n + ' of ' + works.length + ' works';
  }}
  q.addEventListener('input', apply);
  gaps.addEventListener('change', apply);
  apply();
}})();
</script>
'''

if __name__ == '__main__':
    OUT.write_text(render(), encoding='utf-8')
    print(f'{OUT} — {OUT.stat().st_size / 1024 / 1024:.2f} MB')
