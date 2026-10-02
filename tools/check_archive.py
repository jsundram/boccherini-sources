# /// script
# requires-python = ">=3.11"
# ///
"""Assert the invariants this archive is supposed to hold. Run it after any change.

    uv run tools/check_archive.py            # exits non-zero if anything is broken
    uv run tools/check_archive.py --verbose  # list every item behind each count

Every check here exists because the thing it checks for actually went wrong once. The
comments say which, because a bare assertion teaches nobody why it is there.

Known-and-explained exceptions live in `EXPECTED` below rather than being silently
tolerated: if one of them ever gets fixed, this file should shrink.
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

DIG = Path('digitizations')
MEDIA = ('.pdf', '.jpg', '.jpeg', '.png', '.tif')

# Items with no RISM source, each for a reason that has been checked by hand.
EXPECTED_NO_RISM = {
    'US-Wc_M452-A2-B68-op54':
        'Op. 54. No GerB number above 249 appears anywhere in RISM\'s Boccherini records.',
    'btv1b525017368': 'Sinfonia a grande orchestra — not a quartet.',
    'btv1b7400136t': 'Divertimenti with flute obbligato — not a quartet.',
    'btv1b9009885z': 'Première Symphonie, G 500 — not a quartet.',
}


def items():
    for f in sorted(DIG.rglob('metadata.json')):
        d = f.parent
        if any(x.suffix.lower() in MEDIA for x in d.iterdir() if x.is_file()):
            yield d, json.loads(f.read_text())


def urls(v, out=None):
    out = [] if out is None else out
    if isinstance(v, str):
        if '/sources/' in v: out.append(v)
    elif isinstance(v, list):
        for x in v: urls(x, out)
    elif isinstance(v, dict):
        for x in v.values(): urls(x, out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()
    all_items = list(items())
    fails, warns = [], []

    def bad(check, why, who):
        (fails if who else warns).append((check, why, who))

    # 1. Every folder is identified, or is explicitly not a quartet.
    #    Drift here means an item silently stops appearing under its opus on the shelf.
    unid = [d.name for d, m in all_items
            if not (m.get('gerard') or m.get('gerard_numbers'))
            and m.get('form') != 'not-a-quartet']
    bad('identified', 'folders with media but no Gérard number and no not-a-quartet mark', unid)

    # 2. Every folder reaches RISM somehow. Broke once when `rism_related` grew three
    #    shapes (string, list, dict) and each reader picked a different one.
    nolink = [d.name for d, m in all_items
              if not (urls(m.get('source')) + urls(m.get('rism_related'))
                      + urls(m.get('rism_constituents')))]
    bad('rism-link', 'no RISM source link and not a known exception',
        [n for n in nolink if n not in EXPECTED_NO_RISM])

    # 3. One shape for that field, so the next reader cannot pick the wrong one.
    shape = [d.name for d, m in all_items
             if m.get('rism_related') is not None and not isinstance(m['rism_related'], list)]
    bad('rism-shape', '`rism_related` is not a list', shape)

    # 4. A work-level link must say so, or it reads as a link to this copy.
    rel = [d.name for d, m in all_items
           if m.get('rism_relation') not in (None, 'copy', 'work')]
    bad('rism-relation', '`rism_relation` is not one of copy/work', rel)

    # 5. Page images and their collated PDF must agree. A folder holding loose images with
    #    no PDF is un-shareable; one holding a short PDF froze a partial download once
    #    (990005865_D-B had 36 of 61 pages).
    loose, short = [], []
    for d, m in all_items:
        jp = sorted(d.glob('*.jpg'))
        pdf = d / f'{d.name}.pdf'
        if jp and not pdf.exists():
            loose.append(d.name); continue
        if jp and pdf.exists():
            try:
                out = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True,
                                     timeout=60).stdout
                n = int(next(l.split(':')[1] for l in out.splitlines() if l.startswith('Pages')))
                if n < len(jp): short.append(f'{d.name} ({n} < {len(jp)})')
            except Exception:
                short.append(f'{d.name} (unreadable PDF)')
    bad('collated', 'loose page images with no collated PDF', loose)
    bad('collated', 'collated PDF has fewer pages than the images beside it', short)

    # 6. What the filenames encoded must be in the sidecar, because the filenames are gone.
    # Exempt on the fact, not on a portal name: an item supplied as a finished PDF never
    # had page-image filenames to lose. That was hardcoded to 'library-of-congress' and so
    # fired on the first hand-supplied scan from anywhere else.
    noindex = [d.name for d, m in all_items
               if (d / f'{d.name}.pdf').exists() and not m.get('page_index')
               and m.get('arrived_as') != 'pdf']
    bad('page-index', 'collated but no page_index recording what the filenames said', noindex)

    # 7. All three page-writing paths in the harvester must respect a collated PDF.
    #    Guarding one and not the others refetched 99 images before it was noticed.
    src = Path('tools/rism_digitizations.py').read_text()
    if src.count('pdf_is_complete(') < 4:      # 1 definition + 3 call sites
        bad('harvester-guard',
            f'pdf_is_complete is referenced {src.count("pdf_is_complete(")}x; expected 4 '
            '(its definition plus all three download paths)', ['tools/rism_digitizations.py'])

    # 8. Every folder must be findable from a RISM record -- as a copy of it, as the
    #    parent volume containing it, or as another copy of the same edition. Otherwise a
    #    scan exists that nobody looking things up in RISM will ever reach. `by_rism`
    #    deliberately excludes edition-level links, which once made 34 folders invisible.
    conc = Path('concordance.jsonl')
    if conc.exists():
        reach, stray = set(), []
        for line in conc.read_text().splitlines():
            r = json.loads(line)
            reach |= set(r.get('held') or []) | set(r.get('held_edition') or [])
            stray += [f'{f} -> {r["rism"]}'
                      for f in sorted(set(r.get('held_any') or []) - set(r.get('held') or []))]
        unreach = sorted({str(d.relative_to(DIG)) for d, _ in all_items} - reach)
        bad('concordance-reach',
            'on disk but unreachable from any RISM record (rebuild with `uv run '
            'concordance.py` if stale)',
            [u for u in unreach if u.split('/')[-1] not in EXPECTED_NO_RISM])
        # 8b. A "copy" claim must land on a holding: the record lists the folder's library,
        #     at a shelfmark that does not contradict it. Eight folders once claimed to be
        #     copies of records with no holding at their library, and the concordance
        #     credited them to whichever libraries the record did list. If the record is
        #     the same music elsewhere, `boc link <folder> --rism <id> --relation work`;
        #     if it is the wrong record, `--drop`.
        bad('copy-unplaced',
            '"copy" of a RISM record with no matching holding at this library',
            stray)
    else:
        bad('concordance-reach', 'concordance.jsonl missing — run `uv run tools/concordance.py`',
            ['concordance.jsonl'])

    # 9. The structure store should cover every item, so that "not read" is a recorded
    #    fact rather than an absence. Manuscripts are recorded as skipped, with the reason.
    store = Path('structure')
    if store.exists():
        have = {p.stem for p in store.glob('*.json')}
        missing = sorted({d.name for d, _ in all_items} - have)
        if missing:
            bad('structure-store',
                'no structure reading recorded (run `uv run boc.py build`)',
                missing)

    # 10. Nothing derived may be older than what it was derived from. Two published
    #     artefacts have already gone out stale -- a concordance whose folders had since
    #     moved, and a shelf missing data added an hour earlier -- and both were caught by
    #     luck. `pipeline.py` declares the dependencies; this enforces them.
    try:
        import pipeline
        drift = [st['name'] for st in pipeline.STAGES
                 if not st.get('always') and pipeline.stale(st)]
        bad('stale', 'derived files older than their inputs (run `uv run boc.py build`)', drift)
    except Exception as e:
        bad('stale', f'could not check staleness: {e}', ['pipeline.py'])

    # 11. No number in a document may disagree with the data. Counts live in
    #     `<!-- stats:… -->` blocks that `stats.py` fills; if one is out of date the
    #     documentation is lying, which is how STATE-OF-EVIDENCE.md said 82 for 76.
    try:
        r = subprocess.run(['uv', 'run', 'tools/stats.py', '--check'], capture_output=True,
                           text=True, timeout=600)
        if r.returncode:
            bad('doc-stats', 'generated numbers in the docs are out of date '
                '(run `uv run boc.py build`)',
                [l.split(':', 1)[-1].strip() for l in r.stderr.splitlines()
                 if 'out of date:' in l] or ['see stats.py --check'])
    except Exception as e:
        bad('doc-stats', f'could not check doc statistics: {e}', ['stats.py'])

    # 12. Every authored claim must say where it came from. A Gérard number or a RISM link
    #     with no provenance is indistinguishable from a guess, and this archive has been
    #     bitten by exactly that. `claim.py` always writes one; hand edits may not.
    noprov = []
    for d, m in all_items:
        if (m.get('gerard_numbers') or m.get('gerard')) and (
                m.get('gerard_established_by') or m.get('established_by')
                or m.get('corrected') or m.get('rism_relation') == 'copy'):
            pass
        elif m.get('gerard_numbers') or m.get('gerard'):
            noprov.append(d.name)
        v = m.get('contents_verified')
        if isinstance(v, dict) and not (v.get('found') or v.get('how')):
            noprov.append(f'{d.name} (verified with no account of what was seen)')
    bad('provenance', 'a label with no statement of where it came from '
        '(use `uv run boc.py label`)', noprov)

    # 13. Overrides must point at something that exists, or they are silently dead.
    for name, key in (('thumbnails.json', None), ('corrections.json', None)):
        try:
            data = json.loads(Path(name).read_text())
        except Exception:
            continue
        keys = [k for k in data if not k.startswith('_')]
        if name == 'thumbnails.json':
            known = {d.name for d, _ in all_items}
            bad('overrides', f'{name} keys matching no folder',
                [k for k in keys if k not in known])
        else:
            cached = {p.stem for p in Path('.rism-cache').glob('*.xml')}
            bad('overrides', f'{name} keys matching no RISM record',
                [k for k in keys if k not in cached])

    # 14. A command printed in a document must exist. Moving the scripts into `tools/`
    #     left 48 examples across 9 documents pointing at paths that were no longer there,
    #     and every one of them would have failed on the first paste. Documents are
    #     instructions; an instruction that cannot run is worse than none.
    stale_cmd = []
    docs = [d for d in Path('.').rglob('*.md')] + [
        Path('boc.py'), *Path('tools').rglob('*.py')]
    for doc in sorted(docs):
        if '.rism-cache' in str(doc) or '__pycache__' in str(doc): continue
        for i, line in enumerate(doc.read_text().splitlines(), 1):
            for m in re.finditer(r'uv run ([\w/.\-]+\.py)', line):
                if not Path(m.group(1)).exists():
                    stale_cmd.append(f'{doc}:{i} -> {m.group(1)}')
    bad('doc-commands', 'a document or script naming a command that is not there', stale_cmd)

    # 15. A document a stage writes must say so. Fifteen documents here are meant to be
    #     edited and eight are overwritten on the next build; they looked identical, so
    #     editing the wrong one lost the edit silently.
    try:
        import pipeline
        unstamped = [str(w) for st in pipeline.STAGES for w in st['writes']
                     if str(w).endswith('.md') and Path(w).exists()
                     and pipeline.BANNER not in Path(w).read_text()]
        bad('doc-generated', 'generated documents not marked as generated', unstamped)
    except Exception as e:
        bad('doc-generated', f'could not check: {e}', ['pipeline.py'])

    # 16. An irreplaceable item must still be byte-for-byte what was declared. Everything
    #     else here can be fetched again; these cannot, so corruption that nothing detects
    #     is the real risk, not deletion.
    try:
        sys.path.insert(0, 'tools')
        import originals
        ok_n, changed, missing = originals.verify()
        bad('originals-changed', 'irreplaceable files no longer match their checksum', changed)
        bad('originals-missing', 'irreplaceable files that are gone', missing)
    except Exception as e:
        bad('originals', f'could not verify irreplaceable items: {e}', ['originals.py'])

    # 17. Every item must have a way back: an address it can be fetched from again, or a
    #     declaration that it cannot be. The two purchased Library of Congress scans sat in
    #     the archive for weeks with neither, and nothing would ever have said so.
    try:
        declared = set(originals.load())
        adrift = []
        for d, m in all_items:
            rel = str(d.relative_to(Path('digitizations')))
            if rel in declared: continue
            if any(m.get(k) for k in ('url', 'manifest', 'ark', 'mets', 'bne_digital_url')):
                continue
            adrift.append(rel)
        bad('no-way-back', 'items with no address to re-fetch from and no `boc protect` '
                           'declaration', adrift)
    except Exception as e:
        bad('no-way-back', f'could not check: {e}', ['originals.py'])

    print(f'{len(all_items)} items checked\n')
    ok = True
    for check, why, who in fails + warns:
        if not who: continue
        ok = False
        print(f'  FAIL  [{check}] {why}: {len(who)}')
        for x in (who if a.verbose else who[:6]):
            print(f'          {x}')
        if not a.verbose and len(who) > 6:
            print(f'          … and {len(who) - 6} more (--verbose)')
    if EXPECTED_NO_RISM:
        print(f"\n  {len(EXPECTED_NO_RISM)} items have no RISM source, each explained in "
              f"EXPECTED_NO_RISM:")
        for k, v in EXPECTED_NO_RISM.items():
            print(f'      {k:24} {v}')
    print('\nall invariants hold' if ok else '\nsomething drifted — see above')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
