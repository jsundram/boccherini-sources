# Working in this archive

Scans of Boccherini's string quartets, keyed to the Gérard catalogue and tied back to RISM.

## Use `boc`. Do not call the other scripts directly.

```sh
uv run boc.py                 # the verb list
uv run boc.py status          # where things stand
uv run boc.py todo            # what needs a person
uv run boc.py check           # the invariants — run before saying anything is done
```

`boc.py` is the only script in the root. The rest live in `tools/`, with completed
migrations in `tools/oneoff/` (one of them deletes things) and an unrelated converter in
`tools/mei/`. `boc` wraps what a session needs and rebuilds what a change invalidates;
reaching past it is how this archive shipped stale artefacts more than once.

## Two changes matter, and both have a front door

**Labels** — what is in a PDF. **Linkages** — which RISM record it is a copy of. Everything
downstream trusts both.

```sh
uv run boc.py label <folder> --gerard 242,243,244 --saw "what you actually saw"
uv run boc.py link  <folder> --rism 840013721 --relation copy --saw "..."
uv run boc.py confirm <folder> --saw "..."
```

These validate the number against `opera.json` and the id against the RISM cache, demand
evidence, write to the layer that owns the fact, and rebuild afterwards.

**Never hand-edit** `digitizations/*/metadata.json`, `structure/*`, or any file a stage in
`pipeline.py` lists as an output. The harvester rewrites sidecars from RISM on every run:
a Gérard number written into one is silently reverted. That has happened twice.

## Taking in someone else's scans

`digitizations/INTAKE-SPEC.md` is the contract, and the code is its authority — the field
table lives in `tools/check_intake.py`, the mapping in `tools/adapt_intake.py`.

```sh
uv run boc.py intake <upstream-dir> --report   # what it resolves from RISM, and on what evidence
uv run boc.py intake <upstream-dir>            # copy in and write metadata
uv run boc.py vet <folder>                     # errors block intake, warnings name what degrades
```

Resolve the Gérard number from what the manuscript says about itself — the date it carries —
and verify it against RISM. Never from the filename: the `Vma ms 1067` PDFs arrived labelled
*Opus 48 Number 1–4* for pieces that are Op. 48 nos. 3–6.

## Scans that exist nowhere else

Everything harvested from a portal has a recovery plan: `source` names where it came from and
the harvester can fetch it again. A scan someone made from the shelf has none, so the risk
inverts — silent corruption matters more than deletion, because nothing would ever tell you.

```sh
uv run boc.py protect --declare <folder> --from "who gave it to you"
uv run boc.py protect                 # verify every declared file, byte for byte
```

That records a checksum per file in `originals.jsonl`, `boc check` fails if one changes or
goes missing, and the destructive tools skip the folder — an irreplaceable item's page
images are never traded for a collated PDF, whatever the PDF verifies. Do not put these
facts in the item's `metadata.json`: the harvester rewrites sidecars from RISM.

## Never write a number into a document

Counts go stale silently. `STATE-OF-EVIDENCE.md` said 82 where the answer was 76 within an
hour of being written by hand.

Documents carry the *process*: "run `uv run boc.py status`". Where a count must appear, it
goes in a `<!-- stats:name -->` block that `stats.py` fills, and `boc check` fails while any
is out of date. Historical findings — "the Berlin search returned 74 results on 2026-09-28"
— keep their numbers, because those record what was true on a date.

## Before claiming anything is finished

```sh
uv run boc.py build && uv run boc.py check
```

`check` asserts that every item is identified or marked not-a-quartet, that every one is
reachable from a RISM record, that no derived file is older than its inputs, that no
generated number in the docs has drifted, and that every label says where it came from.
If it passes, the archive means what the documents say. If it fails, it names the file.

A stage is judged stale by the content of its inputs, so rewriting a sidecar or a reading
with the same bytes costs nothing. Code is the exception: renaming a script rewrites a path
string in every file that calls it, and the bytes really do change even though an hour of
OCR would land on the same answer. When a *code* change cannot affect a stage's output, say
so instead of paying for it:

```sh
uv run boc.py build --assume read      # the inputs changed, the output cannot have
```

That records a fingerprint of the stage's inputs as vouched-for, so it is an assertion on
the record rather than a decision someone made once and forgot. Never use it to skip a stage
you merely expect to be unchanged — if it might have moved, run it.

The way to earn the assertion rather than guess at it is to run the stage on one item and
diff, which for `read` takes a minute against the forty-six the whole stage costs:

```sh
cp structure/<id>.json "$TMPDIR/before"
uv run tools/read_structure.py digitizations/<Gnnn>/<id> --write
diff "$TMPDIR/before" structure/<id>.json     # identical: the reader is deterministic
```

A vouch that turns out to be wrong is cleared by `uv run boc.py build --all`, which runs
every stage regardless and records what it finds. That is the escape hatch — do not
hand-edit `.pipeline-state.json`.

## What the machines cannot do

OCR reads engraving, not handwriting — every manuscript and autograph is outside it. Work
numbering is unreliable: trust the page a work starts on, not the numeral printed there. And
no structural check asks *"is this the right piece"*, only *"is this shaped like its label"*.

`digitizations/STATE-OF-EVIDENCE.md` says what stands behind every label and what still
needs eyes. The loop for working through it:

```sh
uv run boc.py review          # build review.html, open it, decide, export
uv run boc.py apply verdicts.json    # verdicts back in as validated claims
```

## What is still open

`TODO.md` carries the open work and the standing risks. It names commands, not counts, so it
does not go stale — read it before starting something new, and add to it rather than leaving
a finding only in a reply.

## Where to read more

`README.md` is the map. `digitizations/EVIDENCE-CHAIN.md` explains which layer owns which
fact and how to correct each. `STATUS.md` is the narrative, including the mistakes — the
section *Corrections: things I asserted and had to retract* is the most useful part of it.
