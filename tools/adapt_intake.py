# /// script
# requires-python = ">=3.11"
# ///
"""Turn an upstream PDF pipeline's output into archive-shaped items.

The upstream pipeline knows what it photographed and how it built each PDF. It does not
know RISM, and it should not have to: the cache is here. So it supplies the shelfmark and
the date each manuscript carries, and this resolves the RISM source record and the Gerard
number from those -- never from the filename, which for `Vma ms 1067` said "Opus 48 Number
1" for a quartet that is Op. 48 no. 3.

    uv run tools/adapt_intake.py <upstream-dir> --dry-run
    uv run tools/adapt_intake.py <upstream-dir>          # copy in and write metadata
    uv run tools/adapt_intake.py <upstream-dir> --report # what it resolved, and how

It reads `derivation.json`:

    collection: {shelfmark, repository, city, photographer, photo_date, siglum?}
    quartets:   [{id, pdf, title, opus, gerard?, dated, parts{name: pages}}]
    pages:      [{page, photo, sha256, ...}]

`siglum` is optional -- the repository name resolves to one via RISM's own institution
records. `gerard` is optional and is verified rather than trusted when present.

Nothing is moved. Files are copied, and the source directory is left untouched.
"""
import argparse, json, re, shutil, subprocess, sys, unicodedata
from pathlib import Path

DIG = Path('digitizations')
CACHE = Path('.rism-cache')
MONTHS = {'gennaro': 1, 'gennaio': 1, 'febraro': 2, 'febrajo': 2, 'febbraio': 2,
          'marzo': 3, 'aprile': 4, 'maggio': 5, 'giugno': 6, 'luglio': 7,
          'agosto': 8, 'settembre': 9, 'ottobre': 10, 'novembre': 11,
          'decembre': 12, 'dicembre': 12}


def flat(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    return re.sub(r'[^a-z0-9]', '', s.lower())


def field(x, tag, sub):
    out = []
    for m in re.finditer(rf'<(?:marc:)?datafield[^>]*tag="{tag}"[^>]*>(.*?)'
                         rf'</(?:marc:)?datafield>', x, re.S):
        for s in re.finditer(rf'<(?:marc:)?subfield[^>]*code="{sub}"[^>]*>(.*?)</',
                             m.group(1), re.S):
            out.append(re.sub(r'\s+', ' ', s.group(1)).strip())
    return out


def cached():
    """Every cached RISM source, with what we need to match on."""
    for f in sorted(CACHE.glob('*.xml')):
        x = f.read_text()
        yield dict(id=f.stem,
                   title=(field(x, '245', 'a') or [''])[0],
                   siglum=(field(x, '852', 'a') or [''])[0],
                   shelf=(field(x, '852', 'c') or [''])[0],
                   institution=(field(x, '852', 'e') or [''])[0],  # RISM puts the library in $e
                   gerard=(field(x, '690', 'n') or [''])[0],
                   medium=(field(x, '593', 'a') or [''])[0],
                   extent=(field(x, '300', 'a') or [''])[0],
                   date=(field(x, '260', 'c') or [''])[0])


def siglum_for(repository, recs):
    for r in recs:
        if r['institution'] and flat(r['institution']) == flat(repository):
            return r['siglum']
    for r in recs:                          # a prefix is enough: RISM spells these variously
        if r['institution'] and flat(repository).startswith(flat(r['institution'])[:24]):
            return r['siglum']
    return ''


def month_of(text):
    t = flat(text)
    for name, n in MONTHS.items():
        if flat(name) in t:
            return n
    return None


def resolve(q, vol_shelf, siglum, recs):
    """Which RISM source is this quartet? Returns (record, how, note)."""
    def same_volume(r):
        """Our volume shelfmark and RISM's, either way round: RISM writes
        'VMA MS-1067 (1-6)' where the collection calls itself 'Vma ms 1067'."""
        a, b = flat(vol_shelf), flat(r['shelf'])
        return bool(a and b and (a in b or b in a))

    pool = [r for r in recs
            if r['siglum'] == siglum and same_volume(r) and r['gerard']]
    if not pool:
        return None, 'unresolved', f'no cached RISM source at {siglum} {vol_shelf}'

    want = month_of(q.get('dated', ''))
    if want:
        hit = [r for r in pool if month_of(r['title']) == want]
        if len(hit) == 1:
            m = [k for k, v in MONTHS.items() if v == want][0]
            return hit[0], 'month', (
                f"the manuscript dates itself \"{q['dated']}\"; RISM {hit[0]['id']} titles "
                f"this source \"{hit[0]['title']}\". Matched on the month ({m}), not on the "
                f"supplied filename.")
        if len(hit) > 1:
            return None, 'ambiguous', f'{len(hit)} sources share that month'

    # no month: fall back to a Gerard number the upstream asserted, verified against RISM
    if q.get('gerard'):
        g = re.sub(r'^\s*(?:GerB|Ger|G)?[.\s]*', '', str(q['gerard'])).strip()
        hit = [r for r in pool if r['gerard'] == g]
        if len(hit) == 1:
            return hit[0], 'gerard-asserted', (
                f'upstream asserted G {g}; RISM {hit[0]["id"]} carries GerB {g} at this '
                f'shelfmark, so the assertion checks out.')
        if hit:
            return None, 'ambiguous', (
                f'upstream asserted G {g} and {len(hit)} RISM sources at this shelfmark '
                f'carry it: {", ".join(r["id"] for r in hit)}')
        return None, 'gerard-refuted', (
            f'upstream asserted G {g}, which no RISM source at this shelfmark carries')
    return None, 'ambiguous', (
        f'{len(pool)} candidate sources and nothing to choose between them: give `dated` '
        f'(the date the manuscript carries) or `gerard`')


def build(up, dry=False, report=False, force=False):
    der = json.loads((up / 'derivation.json').read_text())
    col, quartets = der['collection'], der['quartets']
    recs = list(cached())
    siglum = col.get('siglum') or siglum_for(col.get('repository', ''), recs)
    if not siglum:
        sys.exit(f"cannot resolve a siglum for {col.get('repository')!r}; "
                 'add `siglum` to derivation.json:collection')
    vol = col.get('shelfmark', '')
    vol_bare = re.sub(rf'^\s*{re.escape(siglum)}\s*,?\s*', '', vol).strip()
    print(f'{siglum} · {vol_bare} · {len(quartets)} item(s) · photographed by '
          f'{col.get("photographer", "?")} on {col.get("photo_date", "?")}\n')

    made, failed, skipped = [], [], []
    for q in quartets:
        rec, how, note = resolve(q, vol_bare, siglum, recs)
        if not rec:
            failed.append((q['id'], how, note))
            print(f"  {q['id']:10} UNRESOLVED  ({how}) {note}")
            continue
        g, pos = rec['gerard'], q['id'].rsplit('-', 1)[-1]
        d = DIG / f'G{g}' / f'{rec["id"]}_{siglum}'
        src = up / q['pdf']
        print(f"  {q['id']:10} -> G {g:4} {rec['id']}  [{how}]  {d.relative_to(DIG)}")
        if report:
            print(f'             {note}')
        if dry or report:
            continue
        if (d / 'metadata.json').exists() and not force:
            print(f'             EXISTS — left alone. Regenerating would discard whatever '
                  f'has been established by hand since. Pass --force to overwrite.')
            skipped.append(str(d.relative_to(DIG)))
            continue
        d.mkdir(parents=True, exist_ok=True)
        pdf = d / f'{rec["id"]}_{siglum}.pdf'
        shutil.copy2(src, pdf)                                  # copy, never move
        for aux in ('page-index.md', 'derivation.json'):
            if (up / aux).exists():
                shutil.copy2(up / aux, d / aux)
        n = int(subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True)
                .stdout.split('Pages:')[1].split()[0])
        meta = {
            'source': 'private-photography',
            'medium': 'manuscript' if 'manuscript' in rec['medium'].lower() else None,
            'form': 'quartet',
            'title': f"{vol_bare} ({pos}) — {q.get('title') or rec['title']}",
            'composer': 'Boccherini, Luigi (1743-1805)',
            'opus': q.get('opus'),
            'gerard': g,
            'gerard_numbers': [g],
            'gerard_label': g,
            'siglum': siglum,
            'institution': col.get('repository') or rec['institution'],
            'shelfmark': f'{vol_bare} ({pos})',
            'holding': rec['shelf'],
            'pages': n,
            'parts': list(q.get('parts') or []),
            'files': {'all': pdf.name},
            'arrived_as': 'pdf',
            'arrived_as_note': 'Supplied as a finished PDF; no page-image filenames to lose.',
            'source_id': rec['id'],
            'rism_relation': 'copy',
            'rism_related': [f'https://rism.online/sources/{rec["id"]}'],
            'date_statement': (f"Dated {q['dated']} on the manuscript; this copy "
                               f"{rec['date']} per RISM" if q.get('dated') else rec['date']),
            'photographed_by': col.get('photographer'),
            'photographed_on': col.get('photo_date'),
            'photographed_at': f"{col.get('repository')}, {col.get('city')}",
            'irreplaceable': True,
            'derived_from_photographs': True,
            'gerard_corroborated_by': f'Resolved by {how}. {note}',
        }
        meta = {k: v for k, v in meta.items() if v not in (None, '', [], {})}
        (d / 'metadata.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False) + '\n')
        made.append(str(d.relative_to(DIG)))

    print()
    if made:
        print(f'{len(made)} item(s) written. Next:')
        print('  uv run tools/check_intake.py ' + ' '.join(f'digitizations/{x}' for x in made[:2])
              + (' …' if len(made) > 2 else ''))
        print(f'  uv run boc.py protect --declare <folder> --from "..."   # each one')
        print('  uv run boc.py build && uv run boc.py check')
    if skipped:
        print(f'{len(skipped)} already present and left untouched.')
    if failed:
        print(f'{len(failed)} unresolved — nothing was written for those.')
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('upstream')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--report', action='store_true',
                    help='resolutions and the evidence; writes nothing')
    ap.add_argument('--force', action='store_true',
                    help='overwrite an item that already exists, discarding hand edits')
    a = ap.parse_args()
    up = Path(a.upstream)
    if not (up / 'derivation.json').exists():
        sys.exit(f'{up}: no derivation.json')
    sys.exit(build(up, a.dry_run, a.report, a.force))


if __name__ == '__main__':
    main()
