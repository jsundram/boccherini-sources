# /// script
# requires-python = ">=3.11"
# ///
"""One command to bring every derived file up to date, in the right order.

    uv run tools/pipeline.py              # run only what is stale
    uv run tools/pipeline.py --check      # say what is stale, change nothing
    uv run tools/pipeline.py --all        # run everything
    uv run tools/pipeline.py --from audit # this stage and everything after it

There are a dozen scripts here and the order between them mattered, but the order lived
only in somebody's memory. The result was predictable: a concordance published after its
folders had moved, a shelf that did not show data added an hour earlier. Both were caught
by luck rather than by design.

So the dependencies are declared below instead. Each stage names what it reads and what it
writes; a stage is stale when any input is newer than any output, or an output is missing.
`--check` reports that without doing anything, and `check_archive.py` refuses to pass while
anything is stale — so "I forgot to re-run it" stops being a failure mode.

The order is not arbitrary:

  harvest    RISM is upstream of everything; it also rewrites the sidecars
  enrich     fills fields the harvest leaves empty, from what RISM already says
  labels     preserves what filenames encoded, before anything else reads them
  read       OCR: slow, and only re-run when the scans change
  derive     concordance, audits, comparisons — all read sidecars + structure
  publish    the two HTML pages, which read everything above
  verify     the invariants, last, so a failure means a real problem
"""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path

DIG = Path('digitizations')


# Several stages write their reports *into* digitizations/, which is also where the data
# they read lives. Treating the whole tree as an input therefore made every stage
# permanently stale -- each run moved the directory's timestamp past its own output. The
# real input is the sidecars and the scans, not the documents generated beside them.


def generated():
    """Filenames that are *output*, so they never count as input.

    Derived from the stage declarations rather than listed by hand: a hand-kept list was
    edited twice and neither edit took, which left the pipeline permanently stale and the
    reason invisible. If a stage writes it, it is output — that is the whole rule."""
    out = {'README.md',        # every item folder's README is written by the harvester
           'AUTOMATION.md'}    # carries a generated <!-- stats:... --> block
    for st in STAGES:
        for w in st['writes']:
            out.add(Path(w).name)
    return out


def newest(paths):
    t = 0
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in p.rglob('*'):
                if is_input(f):
                    t = max(t, f.stat().st_mtime)
        elif p.exists():
            t = max(t, p.stat().st_mtime)
    return t


def oldest(paths):
    ts = []
    for p in paths:
        p = Path(p)
        if not p.exists(): return 0          # missing output: definitely stale
        ts.append(p.stat().st_mtime)
    return min(ts) if ts else 0



STAGES = [
    dict(name='harvest', cmd=['uv', 'run', 'tools/rism_digitizations.py', '--download', '--full'],
         reads=['tools/rism_digitizations.py', 'corrections.json', '.rism-cache'],
         writes=[DIG / 'INDEX.md', DIG / 'inventory.jsonl', DIG / 'UNLINKED-HOLDINGS.md',
                 DIG / 'MANUAL-DOWNLOADS.md'],
         note='re-reads RISM and rewrites every sidecar; slow, needs network'),
    dict(name='enrich', cmd=['uv', 'run', 'tools/normalize_metadata.py'],
         reads=['tools/normalize_metadata.py', DIG / 'INDEX.md'],
         writes=[], always=True,
         note='publisher from title imprints, one shape for rism_related; idempotent'),
    dict(name='labels', cmd=['uv', 'run', 'tools/preserve_page_labels.py'],
         reads=['tools/preserve_page_labels.py'], writes=[], always=True,
         note='keeps what page filenames encoded'),
    dict(name='collate', cmd=['uv', 'run', 'tools/collate_pdfs.py'],
         reads=['tools/collate_pdfs.py'], writes=[], always=True,
         note='one PDF per image run; writes nothing when current'),
    # `reads` left out DIG for months: the stage that reads every PDF in the archive did
    # not depend on the archive, so six new items produced no readings and nothing said so.
    # Safe to declare only because the reader now skips items whose reading is current.
    dict(name='read', cmd=['uv', 'run', 'tools/read_structure.py', '--all', '--write'],
         reads=['tools/read_structure.py', DIG], writes=[Path('structure')],
         slow=True, note='OCR over every print — minutes, not seconds'),
    dict(name='rescore', cmd=['uv', 'run', 'tools/read_structure.py', '--rescore'],
         reads=['tools/read_structure.py'], writes=[], always=True,
         note='re-applies the disagreement rules without re-reading pages'),
    dict(name='concordance', cmd=['uv', 'run', 'tools/concordance.py'],
         reads=['tools/concordance.py', 'tools/evidence.py', 'structure', DIG],
         writes=['concordance.jsonl', DIG / 'CONCORDANCE.md']),
    dict(name='audit', cmd=['uv', 'run', 'tools/audit_contents.py'],
         reads=['tools/audit_contents.py', 'tools/evidence.py', 'structure', DIG],
         writes=[DIG / 'CONTENT-AUDIT.md']),
    dict(name='compare', cmd=['uv', 'run', 'tools/compare_rism.py'],
         reads=['tools/compare_rism.py', '.rism-cache', DIG],
         writes=[DIG / 'RISM-DISAGREEMENTS.md']),
    dict(name='state', cmd=['uv', 'run', 'tools/state_of_evidence.py'],
         reads=['tools/state_of_evidence.py', 'tools/evidence.py', 'structure', DIG],
         writes=[DIG / 'STATE-OF-EVIDENCE.md'],
         note='what stands behind each label — generated, never hand-written'),
    dict(name='stats', cmd=['uv', 'run', 'tools/stats.py'],
         reads=['tools/stats.py', 'tools/evidence.py', 'structure', DIG], writes=[], always=True,
         note='fills the <!-- stats:… --> blocks in the docs'),
    dict(name='review', cmd=['uv', 'run', 'tools/build_review_page.py'],
         reads=['tools/build_review_page.py', 'tools/evidence.py', 'structure', DIG],
         writes=['review.html'], slow=True,
         note='the queue of items needing a person'),
    dict(name='identify', cmd=['uv', 'run', 'tools/suggest_ids.py'],
         reads=['tools/suggest_ids.py', DIG], writes=[DIG / 'TO-IDENTIFY.md']),
    dict(name='shelf', cmd=['uv', 'run', 'tools/build_sources_page.py'],
         reads=['tools/build_sources_page.py', 'tools/evidence.py', 'thumbnails.json', 'structure', DIG],
         writes=['boccherini_sources.html'], slow=True),
    dict(name='incipits', cmd=['uv', 'run', 'tools/build_page.py'],
         reads=['tools/build_page.py', 'boccherini-rism-incipits.jsonl'],
         writes=['boccherini_incipits.html'], slow=True),
    dict(name='verify', cmd=['uv', 'run', 'tools/check_archive.py'],
         reads=[], writes=[], always=True, note='the invariants; last, so a failure is real'),
]


STATE = Path('.pipeline-state.json')


# Content is read for anything this small, and only size and mtime for anything larger.
# Every layer a stage rewrites -- the sidecars, the readings -- is JSON of a few KB, so a
# rewrite that changes nothing registers as nothing. The large files are page images and
# collated PDFs, which only `collate` writes and only when a page is genuinely missing.
# Measured: 596 files, 7 MB, 0.1s.
SMALL = 256_000


def sig(f):
    """What a file contributes to a signature."""
    s = f.stat()
    if s.st_size <= SMALL:
        return f'{f}|'.encode() + hashlib.sha256(f.read_bytes()).digest()
    return f'{f}|{s.st_size}|{int(s.st_mtime)}'.encode()


BANNER = '<!-- generated -->'


def stamp_outputs(st):
    """Mark every document a stage generates as generated, naming what rebuilds it.

    Eight of the twenty-three documents under `digitizations/` are stage outputs and look
    exactly like the fifteen that are meant to be edited. Only one said so, and it named a
    path that had since moved. Hand-editing one is silent: the next build overwrites it.
    Done here rather than in each generator so a new one cannot forget.
    """
    for w in st['writes']:
        w = Path(w)
        if w.suffix != '.md' or not w.exists():
            continue
        lines = w.read_text().splitlines()
        cmd = ' '.join(st['cmd'][2:])
        note = (f'{BANNER}\n*Generated by `uv run {cmd}`. Do not edit — the next build '
                f'overwrites it.*')
        body = [l for l in lines if BANNER not in l
                and not l.startswith('*Generated by ')]
        # after the title if there is one, so the document still reads as a document
        at = 1 if body and body[0].startswith('# ') else 0
        head, rest = body[:at], body[at:]
        while rest and not rest[0].strip():
            rest.pop(0)
        w.write_text('\n'.join(head + ['', *note.split('\n'), ''] + rest) + '\n')


def is_input(f):
    """Prose is not an input, and neither is what the operating system leaves behind.

    The documents live inside `digitizations/`, so editing a sentence in one of them used to
    dirty every stage that walks that directory — six of them, including the two that take
    four minutes each. `.DS_Store` is worse: Finder rewrites it merely for looking at a
    folder, which made the 46-minute OCR stage stale with nobody having touched the data.
    """
    return (f.is_file() and f.suffix != '.md' and not f.name.startswith('.')
            and f.name not in generated())


def walk(root):
    return sorted(f for f in root.rglob('*') if is_input(f))


def fingerprint(st):
    """A signature of a stage's declared inputs."""
    h = hashlib.sha256()
    for p in sorted(str(x) for x in st['reads']):
        p = Path(p)
        if not p.exists():
            # A declared input that is not there is a typo in STAGES, not an empty
            # directory. Left alone it hashes to nothing, stably, so `--assume` would
            # cheerfully vouch for a stage on the strength of no evidence at all.
            sys.exit(f"stage '{st['name']}' declares a missing input: {p}")
        for f in ([p] if p.is_file() else walk(p)):
            h.update(sig(f))
    return h.hexdigest()[:16]


def data_stamp():
    """A signature of the two layers every later stage reads: the item folders and the
    readings."""
    h = hashlib.sha256()
    for root in (DIG, Path('structure')):
        for f in walk(root):
            h.update(sig(f))
    return h.hexdigest()


def vouched():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def stale(st):
    if st.get('always'): return True
    if not st['writes']: return True
    # An `--assume` from a previous run can vouch for these exact inputs. Timestamps cannot
    # tell a change that alters output from one that does not: renaming this directory
    # rewrote a path string inside every script and triggered a full re-OCR that produced
    # byte-identical results. There is no way to detect that automatically, so there is a
    # way to assert it, and the assertion is recorded rather than remembered.
    # A vouch speaks for the inputs only. An output that has gone missing is stale whatever
    # anyone asserted about what produced it.
    if all(Path(w).exists() for w in st['writes']) and \
            vouched().get(st['name']) == fingerprint(st):
        return False
    return newest(st['reads']) > oldest(st['writes'])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--from', dest='start')
    ap.add_argument('--skip', action='append', default=[],
                    help='stage to skip; `--skip harvest --skip read` is the fast path')
    ap.add_argument('--assume', action='append', default=[], metavar='STAGE',
                    help="record that this stage's outputs are already correct for its "
                         'current inputs, without running it. For a change that cannot '
                         'affect output — a rename, a comment, a moved file.')
    a = ap.parse_args()

    names = [s['name'] for s in STAGES]
    begin = names.index(a.start) if a.start in names else 0
    # Dirtiness propagates downstream. Once a stage runs it may have rewritten something a
    # later stage reads, so every stage after it must run too -- otherwise a stage judged
    # "not stale" at the top of the run is stale by the time the run ends. That is exactly
    # how `rescore` (which always runs, and rewrites structure/) left the concordance and
    # the audit behind it.
    plan = [st for i, st in enumerate(STAGES)
            if i >= begin and st['name'] not in a.skip]

    if a.assume:
        state = vouched()
        for name in a.assume:
            st = next((x for x in STAGES if x['name'] == name), None)
            if not st: sys.exit(f'no such stage: {name}')
            state[name] = fingerprint(st)
            print(f"  vouched: {name} is current for its inputs as they stand", file=sys.stderr)
        STATE.write_text(json.dumps(state, indent=1))
        return

    if a.check:
        n = 0
        for st in STAGES:
            if st['name'] in a.skip:
                mark = 'skip'
            elif st.get('always'):
                mark = 'always'          # cheap and idempotent; no output to date-stamp
            elif stale(st):
                mark = 'STALE'; n += 1
            else:
                mark = 'ok'
            print(f"  {mark:7}{st['name']:12} {st.get('note', '')}")
        print(f'\n{n} genuinely stale of {len(STAGES)} stages', file=sys.stderr)
        sys.exit(1 if n else 0)

    # Decided one stage at a time, not planned up front, because whether a stage dirties
    # the ones after it is only known once it has run. Six stages are marked `always`:
    # they are idempotent and declare no output, so they were treated as always dirty, and
    # that alone re-ran the 46-minute OCR on every single build. An `always` stage now
    # dirties what follows only if it actually touched the item folders or the readings.
    ran, dirty = 0, False
    for st in plan:
        if not (a.all or dirty or stale(st)):
            continue
        t0 = time.time()
        print(f"\n--- {st['name']}", file=sys.stderr)
        before = data_stamp() if st.get('always') else None
        r = subprocess.run(st['cmd'])
        if r.returncode:
            sys.exit(f"stage '{st['name']}' failed ({r.returncode}); nothing after it ran")
        ran += 1
        stamp_outputs(st)
        if st.get('always'):
            # reported per stage, not from the latched flag: once anything upstream has
            # dirtied the run, `dirty` says nothing about what this stage did
            touched = data_stamp() != before
            dirty = dirty or touched
            note = '' if touched else ' (changed nothing)'
        else:
            dirty, note = True, ''
            state = vouched(); state[st['name']] = fingerprint(st)
            STATE.write_text(json.dumps(state, indent=1))
        print(f"    {st['name']} ok, {time.time() - t0:.0f}s{note}", file=sys.stderr)
    print(f'\n{ran} stage(s) run', file=sys.stderr)


if __name__ == '__main__':
    main()
