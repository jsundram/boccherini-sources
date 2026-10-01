# Where each fact comes from, and how to correct it

Everything in this archive is one of four kinds of claim. They have a strict order of
precedence, and each is corrected in a different place. Mixing them up is what produced
mislabelled items — Op. 58 recorded as six quartets twice over, folders hiding under a
Gérard span that was never checked.

| layer | what it is | where it lives | regenerable? |
|---|---|---|---|
| **1. RISM** | the catalogue record | `.rism-cache/*.xml` | yes — re-harvest |
| **2. Harvest** | RISM's record, written next to the scan | `digitizations/*/metadata.json` | yes — `rism_digitizations.py` |
| **3. Reading** | what a machine saw on the pages | `structure/<scan-id>.json` | yes — `read_structure.py --all --write` |
| **4. Looking** | what a person saw on the pages | `contents_verified`, `corrections.json` | **no — authored** |

**Precedence runs downward: 4 beats 3 beats 2 beats 1.** A person who has looked outranks a
machine that has read, which outranks a label inherited from a catalogue that never saw
this copy.

## Correcting each layer

**RISM is wrong** — it happens: F-Po's seven autographs all carry one shelfmark, `RES-507
(2)`, and only one of them is. Record the truth in **`corrections.json`**, keyed by RISM
source id, with `established_by` saying how you know. Never edit `.rism-cache`.

**The label on our copy is wrong** — the Gérard numbers, the shelfmark, the livraison.
Also `corrections.json`: the harvester rebuilds folder names from RISM on every run, so a
Gérard number that lives only in a sidecar will be silently reverted. This has happened
twice.

**The machine misread the pages** — just re-run it; `structure/` is output, not a record.
If the misreading matters, write what is actually there into `contents_verified` on the
item, and the audit will stop asking.

**Nobody has looked yet** — that is the normal state. `CONTENT-AUDIT.md` counts how many
items have been checked against their pages. It is a small number.

## Recording that you looked

In the item's `metadata.json`:

```json
"contents_verified": {
  "date": "2026-09-29",
  "how": "head-strip contact sheet, all 52 pages",
  "found": "Title page 'Op 58. 1re Partie'. Four part-books — Violino I, Violino II, Viola,
            Violoncello — each running I. / II. / III. Quartetto. Three quartets, not six."
}
```

This survives a harvest (`write_sidecar` merges rather than overwrites), removes the item
from the worklist, and tells the next person what you saw rather than only that you were
satisfied.

## What the reading records

`structure/<scan-id>.json` holds, for each item:

- **`rism`** — what the catalogue says the shape is: extent, number of parts, score or
  parts, how many works. This is the thing being checked against.
- **`observed`** — where each part-book starts and what it is called; where each work
  starts, its tempo, and which Gérard numbers that tempo is compatible with.
- **`disagreements`** — plain sentences where the two do not match.
- **`verified`** — a copy of the human verdict, if there is one, so the file is
  self-explanatory.

Manuscripts are recorded with `read: false` and the reason, rather than left absent: an
item that cannot be read and an item nobody has run yet should not look the same.

## The loop

```sh
uv run tools/read_structure.py --all --write     # read the prints
uv run tools/audit_contents.py                   # what disagrees, ranked
uv run boc.py look digitizations/X    # look at one
#   … record contents_verified …
uv run boc.py check                    # nothing drifted
```

`check_archive.py` asserts that every item has a structure entry, so "not read" stays a
recorded fact.
