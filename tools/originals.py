# /// script
# requires-python = ">=3.11"
# ///
"""Irreplaceable items: the ones that exist nowhere but here.

Everything else in this archive has a recovery plan — `source` names a portal or a RISM
record, and the harvester can fetch it again. A scan someone made from the shelf has no
recovery plan, so the risks invert: deletion matters less than *silent* corruption, because
nothing would ever tell you. A Dropbox sync conflict, a bad copy, bit rot in a file nobody
opens for a year — for a Gallica download that is an inconvenience, and for these it is the
loss of the thing itself.

So every file of an irreplaceable item gets a checksum recorded at intake, `boc check`
verifies them, and the destructive tools skip them.

    uv run tools/originals.py --declare <folder> --from "who gave it to you"
    uv run tools/originals.py --verify          # every recorded file still matches
    uv run tools/originals.py --list

The manifest lives at `originals.jsonl` in the root, not in the item's `metadata.json`,
because the harvester rewrites sidecars from RISM and has silently reverted hand-written
facts twice.
"""
import argparse, hashlib, json, sys
from datetime import date
from pathlib import Path

DIG = Path('digitizations')
MANIFEST = Path('originals.jsonl')


def load():
    if not MANIFEST.exists():
        return {}
    out = {}
    for line in MANIFEST.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[r['folder']] = r
    return out


def save(recs):
    MANIFEST.write_text(''.join(
        json.dumps(recs[k], ensure_ascii=False) + '\n' for k in sorted(recs)))


def digest(f):
    h = hashlib.sha256()
    with f.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def files_of(d):
    """The scan itself, not what we wrote about it. `metadata.json` is rewritten from RISM
    and a folder README is prose meant to be edited; checksumming either would make the
    invariant fire on ordinary work and train everyone to ignore it."""
    return sorted(f for f in d.rglob('*')
                  if f.is_file() and f.suffix not in ('.md', '.json')
                  and not f.name.startswith('.'))


def resolve(name):
    """Accept a folder name or a path."""
    p = Path(name)
    if p.is_dir():
        return p
    hits = [d for d in DIG.rglob('*') if d.is_dir() and d.name == Path(name).name]
    if len(hits) == 1:
        return hits[0]
    sys.exit(f'{name}: {"no such item" if not hits else "ambiguous: " + str(hits)}')


def declare(name, giver, note):
    d = resolve(name)
    fs = files_of(d)
    if not fs:
        sys.exit(f'{d}: no files to protect')
    recs = load()
    rel = str(d.relative_to(DIG))
    recs[rel] = {
        'folder': rel,
        'irreplaceable': True,
        'acquired_from': giver,
        'declared': str(date.today()),
        'note': note or '',
        'files': {str(f.relative_to(d)): digest(f) for f in fs},
    }
    save(recs)
    n = sum(f.stat().st_size for f in fs)
    print(f'{rel}: {len(fs)} file(s), {n/1e6:.1f} MB, checksummed and marked irreplaceable')
    print('  `boc check` now fails if any byte of these changes.')


def verify(verbose=False):
    recs, bad, gone, ok = load(), [], [], 0
    for rel, r in recs.items():
        d = DIG / rel
        for name, want in r['files'].items():
            f = d / name
            if not f.exists():
                gone.append(f'{rel}/{name}')
            elif digest(f) != want:
                bad.append(f'{rel}/{name}')
            else:
                ok += 1
        extra = {str(f.relative_to(d)) for f in files_of(d)} - set(r['files']) if d.is_dir() else set()
        if verbose and extra:
            print(f'  note: {rel} has {len(extra)} file(s) added since it was declared')
    return ok, bad, gone


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--declare', metavar='FOLDER')
    ap.add_argument('--from', dest='giver', default='')
    ap.add_argument('--note', default='')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()

    if a.declare:
        if not a.giver:
            sys.exit('--from is required: who gave it to you is the provenance')
        return declare(a.declare, a.giver, a.note)

    if a.list:
        for rel, r in load().items():
            print(f"{rel:44} {len(r['files']):3} file(s)  from {r['acquired_from']}"
                  f"  declared {r['declared']}")
        return

    ok, bad, gone = verify(verbose=True)
    for x in gone: print(f'  MISSING  {x}')
    for x in bad:  print(f'  CHANGED  {x}')
    print(f'{ok} file(s) verified, {len(bad)} changed, {len(gone)} missing')
    sys.exit(1 if bad or gone else 0)


if __name__ == '__main__':
    main()
