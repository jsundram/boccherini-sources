# /// script
# requires-python = ">=3.11"
# ///
"""Turn exported review verdicts into recorded claims.

    uv run tools/apply_review.py ~/Downloads/review-verdicts.json --dry-run
    uv run tools/apply_review.py ~/Downloads/review-verdicts.json

`review.html` keeps verdicts in the browser and exports them as one JSON file. This applies
them, through the same front door as everything else -- each one becomes a `claim.py` call,
so it is validated, stamped, and written to the layer that owns the fact. Without this the
loop had a manual step in the middle, which is where things get dropped.

A verdict of **confirmed** records that the label is right. **wrong** and **unclear** are
*not* applied: neither says what the right answer is, and guessing one would be worse than
leaving the item in the queue. They are listed so the note you wrote is not lost -- act on
them with `boc label` once you know what the label should be.
"""
import argparse, json, subprocess, sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('file', type=Path)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    try:
        rows = json.loads(a.file.read_text())
    except Exception as e:
        sys.exit(f'cannot read {a.file}: {e}')

    applied, held = 0, []
    for r in rows:
        folder, verdict, note = r.get('folder'), r.get('verdict'), (r.get('note') or '').strip()
        if not folder:
            continue
        if verdict == 'confirmed':
            if not note:
                held.append((folder, 'confirmed but no note — say what you saw'))
                continue
            cmd = ['uv', 'run', 'tools/claim.py', 'confirm', folder, '--saw', note,
                   '--how', 'review queue']
            print(('  would run: ' if a.dry_run else '  ') + ' '.join(cmd[3:6]) + ' …')
            if not a.dry_run:
                p = subprocess.run(cmd, capture_output=True, text=True)
                if p.returncode:
                    held.append((folder, p.stdout.strip() or p.stderr.strip()))
                    continue
            applied += 1
        else:
            held.append((folder, f'{verdict or "no verdict"}'
                                 + (f' — "{note}"' if note else '')))

    print(f"\n{applied} confirmed{' (dry run)' if a.dry_run else ''}", file=sys.stderr)
    if held:
        print(f'{len(held)} not applied — these need a decision, not a flag:', file=sys.stderr)
        for f, why in held:
            print(f'   {f:40} {why[:90]}', file=sys.stderr)
        print('\n   fix one with:  uv run boc.py label <folder> --gerard … --saw …',
              file=sys.stderr)
    if applied and not a.dry_run:
        print('\n   run `uv run boc.py build` to rebuild', file=sys.stderr)


if __name__ == '__main__':
    main()
