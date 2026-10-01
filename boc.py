# /// script
# requires-python = ">=3.11"
# ///
"""One entry point. `uv run boc.py <verb>` — everything a session normally does.

    boc status              where the archive stands
    boc todo                what needs a person, ranked
    boc find "F-Po Rés. 507 (14)"    a citation -> RISM source -> what we hold
    boc show  <folder>      every claim on one item, and which file each lives in
    boc look  <folder>      contact sheet: the structure of an item, in one glance
    boc read  <folder>      OCR its headings and propose what is in it

    boc label <folder> --gerard 242,243,244 --saw "..."     record what is in it
    boc link  <folder> --rism 840013721 --saw "..."         record where it came from
    boc confirm <folder> --saw "..."                        the label is right

    boc build               rebuild everything stale, in dependency order
    boc build --assume read    say a stage is already correct (a rename, a comment)
    boc check               the invariants; fails if anything drifted
    boc review              rebuild review.html, the queue needing eyes
    boc apply  verdicts.json   feed the review queue's export back in

There are 28 scripts in this directory and knowing which to run was itself a source of
error -- the archive has shipped stale artefacts more than once because the right script
was not remembered. This wraps the ones a session actually needs, so the answer to "what
do I run" is always `boc`.

Two rules the verbs enforce, so they cannot be forgotten:

  * changing a **label** (what is in a PDF) or a **linkage** (which RISM record it is)
    goes through `boc label` / `boc link`, which validate and demand evidence;
  * anything derived is rebuilt by `boc build`, never by hand.

`boc check` is the last word. If it passes, the archive means what the documents say.
"""
import subprocess, sys

VERBS = {
    'status':  (['uv', 'run', 'tools/stats.py', '--print'], 'where the archive stands'),
    'todo':    (['uv', 'run', 'tools/audit_contents.py', '--flagged'], 'what needs a person'),
    'find':    (['uv', 'run', 'tools/concordance.py', '--match'], 'resolve a citation'),
    'show':    (['uv', 'run', 'tools/claim.py', 'show'], 'every claim on one item'),
    'look':    (['uv', 'run', 'tools/contact_sheet.py'], 'contact sheet for an item'),
    'read':    (['uv', 'run', 'tools/read_structure.py'], 'OCR an item\'s headings'),
    'label':   (['uv', 'run', 'tools/claim.py', 'label'], 'record what is in it'),
    'link':    (['uv', 'run', 'tools/claim.py', 'link'], 'record where it came from'),
    'confirm': (['uv', 'run', 'tools/claim.py', 'confirm'], 'the label is right'),
    'build':   (['uv', 'run', 'tools/pipeline.py'], 'rebuild everything stale'),
    'check':   (['uv', 'run', 'tools/check_archive.py'], 'the invariants'),
    'review':  (['uv', 'run', 'tools/build_review_page.py'], 'rebuild the review queue'),
    'apply':   (['uv', 'run', 'tools/apply_review.py'], 'apply verdicts exported from review.html'),
    'intake':  (['uv', 'run', 'tools/adapt_intake.py'],
                "adapt an upstream pipeline's output into archive shape"),
    'vet':     (['uv', 'run', 'tools/check_intake.py'],
                'does a folder meet the intake spec?'),
    'protect': (['uv', 'run', 'tools/originals.py'],
                'scans that exist nowhere else: declare, verify, list'),
    'harvest': (['uv', 'run', 'tools/pipeline.py', '--from', 'harvest'],
                're-read RISM, then rebuild (slow, needs network)'),
}
# After a claim, everything derived is stale. Rebuilding by hand is exactly what gets
# forgotten, so the verbs that change data rebuild afterwards on their own.
REBUILDS = {'label', 'link', 'confirm', 'apply'}


def usage(code=0):
    print(__doc__.split('\n\n')[0] + '\n')
    for v, (_, note) in VERBS.items():
        print(f'  {v:9} {note}')
    print('\n  every verb passes its remaining arguments straight through;'
          '\n  `uv run boc.py <verb> --help` for that tool\'s own options')
    sys.exit(code)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help', 'help'):
        usage()
    verb, rest = sys.argv[1], sys.argv[2:]
    if verb not in VERBS:
        print(f'unknown verb: {verb}\n', file=sys.stderr)
        usage(2)
    cmd, _ = VERBS[verb]
    r = subprocess.run(cmd + rest)
    if r.returncode:
        sys.exit(r.returncode)
    if verb in REBUILDS:
        print('\n--- rebuilding what depends on that change', file=sys.stderr)
        r = subprocess.run(['uv', 'run', 'tools/pipeline.py'])
        sys.exit(r.returncode)


if __name__ == '__main__':
    main()
