# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy"]
# ///
"""Build review.html — the queue of items that need a person to look.

    uv run tools/build_review_page.py

Everything here needs eyes because the machines are out of moves: the pages contradict the
label, or the label was asserted and never checked, or nothing supports it at all. Each card
carries what is claimed, what RISM says, what the OCR read, and a picture — so the judgement
can be made without leaving the page.

Verdicts are kept in the browser and exported as one JSON file. `apply_review.py` writes
them into the sidecars as `contents_verified`. Nothing is edited from the page itself: the
archive is only ever changed by a script that can be read and re-run.
"""
import base64, html, io, json, sys
from pathlib import Path

import evidence

DIG = Path('digitizations')
OUT = Path('review.html')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')


def e(s):
    return html.escape(str(s)) if s not in (None, '') else ''


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location('b', 'tools/build_sources_page.py')
    b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

    items = []
    for f in sorted(DIG.rglob('metadata.json')):
        d = f.parent
        if not any(x.suffix.lower() in MEDIA for x in d.iterdir() if x.is_file()): continue
        m = json.loads(f.read_text())
        st = evidence.reading(d.name)
        tier, label = evidence.tier_of(m, st)
        if tier not in 'DEF': continue
        obs = (st or {}).get('observed') or {}
        items.append(dict(
            folder=str(d.relative_to(DIG)), name=d.name, tier=tier, tier_label=label,
            g=m.get('gerard_label') or m.get('gerard'),
            siglum=m.get('siglum'), shelf=m.get('shelfmark'),
            medium=('autograph' if m.get('is_autograph')
                    else m.get('medium') or m.get('record_type')),
            title=(m.get('full_title') or m.get('title') or '')[:220],
            said=m.get('gerard_established_by') or m.get('established_by'),
            rism_extent=(st or {}).get('rism', {}).get('extent'),
            rism_form=(st or {}).get('rism', {}).get('form_declared'),
            rism_parts=(st or {}).get('rism', {}).get('parts_declared'),
            books=[f"{x['part']}@p{x['page']}" for x in (obs.get('part_books') or [])],
            works=[f"p{x['page']} {x['tempo'] or '?'}" for x in (obs.get('work_starts') or [])],
            dis=(st or {}).get('disagreements') or [],
            read=bool(st and st.get('read')),
            link=m.get('ark') or m.get('url') or m.get('source'),
            thumb=(b.thumb(d) or {}).get('big')))
    order = {'E': 0, 'F': 1, 'D': 2}
    items.sort(key=lambda i: (order[i['tier']], i['folder']))

    cards = []
    for i in items:
        facts = []
        if i['rism_extent']: facts.append(('RISM extent', e(i['rism_extent'])))
        if i['rism_form']: facts.append(('RISM form', e(i['rism_form'])))
        if i['books']: facts.append(('parts read', e(', '.join(i['books']))))
        if i['works']: facts.append(('works read', e(', '.join(i['works'][:8]))))
        if not i['read']: facts.append(('OCR', 'not readable — manuscript'))
        if i['said']: facts.append(('label came from', e(i['said'][:180])))
        dl = ''.join(f'<dt>{k}</dt><dd>{v}</dd>' for k, v in facts)
        dis = ''.join(f'<li>{e(x)}</li>' for x in i['dis'])
        img = (f'<img loading="lazy" src="{i["thumb"]}" alt="">' if i['thumb']
               else '<div class="noimg">no preview</div>')
        cards.append(f'''<article class="card" data-tier="{i['tier']}" id="c-{e(i['name'])}"
  data-folder="{e(i['folder'])}" data-g="{e(i['g'])}">
  <div class="shot">{img}</div>
  <div class="body">
    <p class="hd"><span class="tier t{i['tier']}">{i['tier']}</span>
       <b>G {e(i['g']) or '—'}</b> · {e(i['siglum'])} {e(i['shelf'])} · {e(i['medium'])}</p>
    <p class="ttl">{e(i['title'])}</p>
    {f'<ul class="dis">{dis}</ul>' if dis else ''}
    <dl>{dl}</dl>
    <p class="go"><a href="{e(i['link'])}" target="_blank" rel="noopener">open at the library</a>
       · <code>{e(i['folder'])}</code></p>
    <div class="verdict">
      <button data-v="confirmed">label is right</button>
      <button data-v="wrong">label is wrong</button>
      <button data-v="unclear">still unclear</button>
      <input type="text" placeholder="what you saw — this is the part that matters">
      <span class="saved"></span>
    </div>
  </div>
</article>''')

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boccherini Review Queue</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@300;400;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#f6f4ef;--card:#fff;--ink:#1a1a1a;--ink2:#555;--faint:#999;--rule:#ddd9d0}}
:root:not([data-theme="light"]) {{}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg:#17181a;--card:#1f2023;--ink:#ece9e3;--ink2:#b3aea4;--faint:#77736c;--rule:#33353a}}}}
:root[data-theme="dark"]{{--bg:#17181a;--card:#1f2023;--ink:#ece9e3;--ink2:#b3aea4;
  --faint:#77736c;--rule:#33353a}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font:400 16px/1.5 Spectral,Georgia,serif;padding:0 16px 4rem}}
header{{max-width:1080px;margin:0 auto;padding:2rem 0 1rem}}
h1{{font-size:1.5rem;margin:0 0 .3rem}}
.lede{{color:var(--ink2);margin:.2rem 0 1rem;max-width:62ch}}
.bar{{position:sticky;top:0;z-index:5;background:var(--bg);padding:.6rem 0;
  border-bottom:1px solid var(--rule);display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}}
button,select{{font:500 .8rem/1 'IBM Plex Mono',monospace;padding:.42rem .6rem;
  border:1px solid var(--rule);background:var(--card);color:var(--ink);border-radius:3px;
  cursor:pointer}}
button[aria-pressed=true]{{background:var(--ink);color:var(--bg)}}
#count{{color:var(--ink2);font:500 .78rem 'IBM Plex Mono',monospace}}
main{{max-width:1080px;margin:0 auto}}
.card{{display:flex;gap:16px;background:var(--card);border:1px solid var(--rule);
  border-radius:3px;padding:14px;margin:14px 0}}
.card[hidden]{{display:none}}
.shot{{flex:0 0 190px}}
.shot img{{width:190px;height:auto;background:#fff;border:1px solid var(--rule)}}
.noimg{{width:190px;height:120px;display:grid;place-items:center;color:var(--faint);
  border:1px dashed var(--rule);font:500 .7rem 'IBM Plex Mono',monospace}}
.body{{flex:1;min-width:0}}
.hd{{margin:0 0 .3rem;font-size:.95rem}}
.ttl{{margin:.1rem 0 .5rem;color:var(--ink2);font-size:.9rem}}
.dis{{margin:.3rem 0;padding-left:1.1rem;color:#a33}}
.dis li{{font-size:.85rem}}
dl{{display:grid;grid-template-columns:auto 1fr;gap:.1rem .7rem;margin:.5rem 0;
  font:400 .8rem/1.45 'IBM Plex Mono',monospace}}
dt{{color:var(--faint)}} dd{{margin:0;color:var(--ink2);word-break:break-word}}
.go{{margin:.4rem 0 .6rem;font-size:.8rem}}
.go code{{color:var(--faint);font-size:.74rem}}
.verdict{{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center;
  border-top:1px dashed var(--rule);padding-top:.6rem}}
.verdict input{{flex:1;min-width:230px;padding:.42rem .5rem;border:1px solid var(--rule);
  border-radius:3px;background:var(--bg);color:var(--ink);font:400 .85rem Spectral,serif}}
.saved{{font:500 .72rem 'IBM Plex Mono',monospace;color:#2f6d3f}}
.tier{{display:inline-block;min-width:1.1rem;text-align:center;border-radius:2px;
  font:600 .7rem/1.4 'IBM Plex Mono',monospace;color:#fff;padding:0 .2rem}}
.tE{{background:#a33}} .tD{{background:#9a6a3a}} .tF{{background:#777}}
@media (max-width:720px){{.card{{flex-direction:column}} .shot,.shot img{{width:100%;flex:none}}}}
</style></head><body>
<header>
  <h1>Review queue</h1>
  <p class="lede">{len(items)} items the machines cannot settle: the pages contradict the
  label, the label was asserted and never checked, or nothing supports it. Each card shows
  what is claimed, what RISM says, and what the OCR read. Say what you actually saw — that
  sentence is the useful part, more than the verdict.</p>
  <div class="bar">
    <button class="f" data-t="E" aria-pressed="false">contradicted</button>
    <button class="f" data-t="D" aria-pressed="false">asserted</button>
    <button class="f" data-t="F" aria-pressed="false">unsupported</button>
    <button id="undone" aria-pressed="false">not yet done</button>
    <button id="export">export verdicts</button>
    <span id="count"></span>
  </div>
</header>
<main>{''.join(cards)}</main>
<script>
(function(){{
  var KEY='boccherini-review-v1', store={{}};
  try {{ store = JSON.parse(localStorage.getItem(KEY) || '{{}}'); }} catch (e) {{ store = {{}}; }}
  function save() {{
    try {{ localStorage.setItem(KEY, JSON.stringify(store)); }} catch (e) {{}}
  }}
  var cards=[].slice.call(document.querySelectorAll('.card'));
  cards.forEach(function(c){{
    var folder=c.dataset.folder, rec=store[folder]||{{}},
        note=c.querySelector('input'), mark=c.querySelector('.saved');
    if(rec.note) note.value=rec.note;
    function paint(){{
      c.querySelectorAll('.verdict button').forEach(function(b){{
        b.setAttribute('aria-pressed', String(b.dataset.v===rec.verdict));
      }});
      mark.textContent = rec.verdict ? 'saved' : '';
    }}
    c.querySelectorAll('.verdict button').forEach(function(b){{
      b.addEventListener('click',function(){{
        rec.verdict = (rec.verdict===b.dataset.v) ? null : b.dataset.v;
        rec.folder=folder; rec.g=c.dataset.g; rec.date=new Date().toISOString().slice(0,10);
        store[folder]=rec; save(); paint(); apply();
      }});
    }});
    note.addEventListener('input',function(){{
      rec.note=note.value; rec.folder=folder; store[folder]=rec; save();
    }});
    paint();
  }});
  var fs=[].slice.call(document.querySelectorAll('.f')), undone=document.getElementById('undone');
  function apply(){{
    var on=fs.filter(function(b){{return b.getAttribute('aria-pressed')==='true';}})
             .map(function(b){{return b.dataset.t;}}),
        only=undone.getAttribute('aria-pressed')==='true', shown=0;
    cards.forEach(function(c){{
      var ok=true;
      if(on.length && on.indexOf(c.dataset.tier)<0) ok=false;
      if(ok && only && (store[c.dataset.folder]||{{}}).verdict) ok=false;
      c.hidden=!ok; if(ok) shown++;
    }});
    var done=Object.keys(store).filter(function(k){{return store[k].verdict;}}).length;
    document.getElementById('count').textContent=shown+' shown · '+done+' of {len(items)} decided';
  }}
  fs.concat([undone]).forEach(function(b){{
    b.addEventListener('click',function(){{
      b.setAttribute('aria-pressed', b.getAttribute('aria-pressed')==='true'?'false':'true');
      apply();
    }});
  }});
  document.getElementById('export').addEventListener('click',function(){{
    var out=Object.keys(store).filter(function(k){{return store[k].verdict||store[k].note;}})
      .map(function(k){{return store[k];}});
    var blob=new Blob([JSON.stringify(out,null,1)],{{type:'application/json'}}),
        a=document.createElement('a');
    a.href=URL.createObjectURL(blob); a.download='review-verdicts.json';
    document.body.appendChild(a); a.click(); a.remove();
  }});
  apply();
}})();
</script></body></html>'''
    OUT.write_text(page)
    print(f'{len(items)} items needing eyes -> {OUT} ({len(page)/1e6:.2f} MB)', file=sys.stderr)


if __name__ == '__main__':
    main()
