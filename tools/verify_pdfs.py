# /// script
# requires-python = ">=3.11"
# ///
"""Prove every page image survives byte-for-byte inside its collated PDF.

    uv run tools/verify_pdfs.py            # all 88 folders, every page
    uv run tools/verify_pdfs.py --report   # write digitizations/PDF-VERIFICATION.md

`img2pdf` embeds JPEG data without re-encoding, so the bytes in the PDF should be the
bytes on disk. "Should" is not good enough to delete originals on, so this extracts every
image back out with `pdfimages -j` and compares MD5s. A folder passes only if the page
count matches and every single page is identical.

Writes a manifest of per-page checksums so the claim stays checkable later.
"""
import argparse, hashlib, json, subprocess, sys, tempfile
from pathlib import Path

DIG = Path('digitizations')


def md5(b):
    return hashlib.md5(b).hexdigest()


def verify(d):
    jp = sorted(d.glob('*.jpg'))
    pdf = d / f'{d.name}.pdf'
    if not jp:
        return None
    if not pdf.exists():
        return dict(folder=str(d.relative_to(DIG)), ok=False, reason='no collated PDF')
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(['pdfimages', '-j', '-p', str(pdf), f'{td}/x'],
                           capture_output=True, timeout=1800)
        ex = sorted(Path(td).glob('x-*'))
        if len(ex) != len(jp):
            return dict(folder=str(d.relative_to(DIG)), ok=False,
                        reason=f'{len(ex)} images in PDF vs {len(jp)} on disk')
        pages, bad = {}, []
        for src, got in zip(jp, ex):
            a, b = md5(src.read_bytes()), md5(got.read_bytes())
            pages[src.name] = a
            if a != b:
                bad.append(src.name)
        return dict(folder=str(d.relative_to(DIG)), ok=not bad, n=len(jp),
                    reason=f'{len(bad)} pages differ: {bad[:4]}' if bad else '',
                    pages=pages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true')
    a = ap.parse_args()
    folders = sorted({p.parent for p in DIG.rglob('*.jpg')})
    rows, npages = [], 0
    for d in folders:
        r = verify(d)
        if not r:
            continue
        rows.append(r)
        npages += r.get('n', 0)
        print(('  ok   ' if r['ok'] else '  FAIL ') + r['folder']
              + ('' if r['ok'] else '  ' + r['reason']), file=sys.stderr)
    bad = [r for r in rows if not r['ok']]
    print(f'\n{len(rows)} folders, {npages} pages — {len(bad)} failed', file=sys.stderr)
    Path('pdf-verification.jsonl').write_text(
        ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    if a.report:
        L = ['# PDF verification', '',
             f'Every one of the **{npages} page images** in the {len(rows)} collated PDFs was '
             'extracted back out with `pdfimages -j` and compared by MD5 against the file on '
             'disk.', '',
             f'**{len(rows) - len(bad)} of {len(rows)} folders passed.**'
             + ('' if not bad else f' {len(bad)} failed — see below.'), '',
             '`img2pdf` embeds JPEG data without re-encoding, so this is expected; it is '
             'recorded because the originals are only safe to move once it is proven rather '
             'than assumed. Per-page checksums are in `../pdf-verification.jsonl`.', '']
        if bad:
            L += ['## Failures', '', '| folder | why |', '|---|---|']
            L += [f"| `{r['folder']}` | {r['reason']} |" for r in bad]
        (DIG / 'PDF-VERIFICATION.md').write_text('\n'.join(L))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
