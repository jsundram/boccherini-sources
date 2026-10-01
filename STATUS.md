# RISM / Boccherini incipits — status

*Last updated 2026-09-28.*

Started as a one-line bug. RISM catalogues Gérard's Boccherini catalogue under
the siglum **`GerB`** (MARC 690 `$a`, linked to `publications/29`), not the
word "Gérard" — so the regex in `rism_incipits.py` matched nothing and every
incipit came back without a number. Fixed; **643 incipits** now carry Gérard
numbers — verified complete against RISM's own `totalItems`, which is the only
reason that number can be trusted (see pagination, below).

The corpus reached 643 from 620 on 2026-09-28, when the quartet filter was widened:
RISM writes its uniform title in whichever language the cataloguer used, and matching
only the English `Quartets` had been dropping every `Quatuors` record. See
**The `Quatuors` blind spot**, below.

Everything below grew out of that.

---

## What's here

| file | what it is |
|---|---|
| `rism_incipits.py` | harvests RISM Online → `boccherini-rism-incipits.jsonl` |
| `rism_digitizations.py` | harvests MARC 856 → downloads the scans, by G number |
| `find_scans.py` | searches Gallica for scans RISM does not link → `found/`, then filed under their Gérard number |
| `survey_portals.py` | per-library verdict on whether it can be searched by a script |
| `digitizations/` | the scans. `INDEX.md`, `MANUAL-DOWNLOADS.md`, `UNLINKED-HOLDINGS.md`, `GALLICA-SEARCH.md`, `PORTAL-SURVEY.md` |
| `digitizations/found/` | where a Gallica find lands before it has a Gérard number. Only items that cannot have one stay here — the rest are filed under `G<label>/`, because the filesystem is an index and the sidecar carries the provenance |
| `boccherini-rism-incipits.jsonl` | 643 incipits, Boccherini only |
| `.rism-cache/` | 409 cached MARC records (delete to re-fetch) |
| `opera.json` | vendored from quartets.boccherini.org — the G ↔ opus spine |
| `build_page.py` | engraves the incipits → `boccherini_incipits.html` |
| `incipit_convert.py` | P&E / MEI → MusicXML. 845 lines |
| `test_incipit_convert.py` | 52 tests, ~0.6s, no corpus needed |
| `musicxml2ly-shim.sh` | source of the `~/.local/bin/musicxml2ly` fix |
| `VEROVIO-ISSUE.md` | bug report, ready to file |

### Running things

```sh
uv run tools/rism_incipits.py > boccherini-rism-incipits.jsonl   # re-harvest
uv run tools/build_page.py                                       # rebuild the table
uv run tools/mei/incipit_convert.py --check                          # round-trip all 643
uv run tools/mei/incipit_convert.py --g 159 > g159.musicxml          # one work
uv run --with pytest pytest test_incipit_convert.py -q      # fast tests

uv run tools/rism_digitizations.py                     # inventory the 856 links -> stdout
uv run tools/rism_digitizations.py --download --full    # fetch the scans at full resolution
uv run tools/rism_digitizations.py --g 201 --download   # just one Gérard number

uv run tools/find_scans.py                              # search Gallica, write the report
uv run tools/find_scans.py --download                   # ... and fetch the string quartets
uv run tools/oneoff/survey_portals.py                          # which libraries are scriptable
```

Re-running `--download` re-fetches nothing: every file already on disk is skipped,
so an interrupted run resumes. Delete a directory to force it again.

### Published pages

- **Boccherini Incipit Table** — <https://claude.ai/artifact/YNBZd5PduJBFr3t6KnWqWR>
  All 91 quartets on the Periodic Table layout, every incipit engraved from
  Plaine & Easie, each card's bottom strip showing how many of its movements
  RISM actually indexed.
- **Music Encoding Field Guide** — <https://claude.ai/artifact/JM1SnfoDos1xi2wcE5Jiyf>
  Eight formats on a richness axis, a conversion matrix sourced cell by cell,
  ten rendering engines, links to every standard and repository.

---

## Findings

**Op. 42–48 is a black hole twice over.** G 216–231 — the same works the
recordings chart marks as unrecorded — have *only* their opening movement
indexed in RISM. Across all 91 quartets: **149 of 243 movements** have an
incipit, 42 complete, 35 partial, **14 with nothing at all**, including every
one of Op. 58.

**RISM's opus numbers contradict each other** across sources for about a third
of these works — the Op. 1 / Op. 2 tangle especially. That's why the Gérard
number is the spine and the opus is treated as a majority reading.

**Four undocumented Plaine & Easie rules**, each of which silently corrupted
output until found. Worth a PR to
[`rism-digital/pae-code-spec`](https://github.com/rism-digital/pae-code-spec):

1. `t` attaches to the **preceding** note. `4Ct` trills C; `4tC` is ignored.
2. `r` **terminates** a grace group. Without it the group swallows the rest
   of the bar and every following note becomes ornamental.
3. `(X)` around one note is a **fermata**; around a group it's a **tuplet**.
4. Tuplets are always N-in-the-space-of-2. `;7:4` parses but still means 7:2,
   so a genuine 5:4 cannot be written — and fails silently if you try.

**One real Verovio bug.** `renderToPAE()` emits `@data:` followed by a
newline; Verovio's own PAE reader then parses **zero notes** while
`loadData()` returns `True`. Silent total loss. See `VEROVIO-ISSUE.md`.

**P&E → MusicXML is the one gap worth filling.** Verovio reads P&E, MusicXML,
MEI, `**kern`, ABC and MuseData, and writes SVG, MEI, MIDI, Humdrum and P&E —
but never MusicXML. That's all `incipit_convert.py` does now.

---

## Digitizations: what RISM links, and what it doesn't

`rism_digitizations.py` reads MARC **856** off the same cached records as the
incipit harvest, so an inventory costs no network. Output is keyed on the Gérard
number, with `metadata.json` and a readable `README.md` beside every set of
images, and three generated documents at the top.

**Only a third of 856 is music.** 292 links over 181 quartet sources, and `$x`
is what separates them:

| `$x` | what it is | fetchable |
|---|---|---|
| `IIIF manifest (digitized source)` | a digitized book on RISM's own server | yes |
| `$q image/jpeg` | page photos attached in Muscat | yes |
| `Digitized` | a **landing page** at the holding library | via a resolver |
| `Other` | catalogue cards, watermark databases, microfilm notes | no — not the music |

200 of the 292 are `Other`. Treating 856 as "the digitization field" would have
downloaded a pile of RISM card scans from Dresden.

**Landing pages each needed their own resolver**, and none of them advertises it:

- **Staatsbibliothek Berlin** (34 links) hides the manifest key in a redirect —
  `resolver.../SBB0001C5D2...` 302s to a viewer URL whose `PPN=` is the only
  thing `content.staatsbibliothek-berlin.de/dc/<PPN>/manifest` accepts. The
  `SBB…` id itself 404s.
- **Rochester / Sibley** (29 links): the handle server for prefix `1802` returns
  *Cannot Connect to Server*, but the Handle **REST API** still resolves, and the
  page behind it carries per-part PDFs whose instrument name lives only in
  `Content-Disposition` — `39087009315336.viola.pdf`.
- **MDZ** and **Gallica** are derivable from the URN and the ark. Gallica 403s
  any unfamiliar user-agent.
- **Harvard** serves a 200 HTML "this resource has moved" page with a meta
  refresh where a manifest should be, so the reader follows meta refreshes
  before concluding something isn't IIIF.

**RISM's own IIIF server caps every request at 1000px** (`level1`,
`maxWidth: 1000`) although the scans are ~3500×4500. It honours region requests,
so `--full` fetches each page as 1000px tiles and stitches them — 20 requests a
page. Servers that don't cap return full size in one request, so the flag only
costs anything on RISM.

### RISM pagination ends early, silently — this one affects the incipits too

Three runs of the same query returned **613, 462 and 528** source ids. RISM
intermittently serves a page with no `view.next`, which ends the walk. Nothing
errors and nothing looks wrong; you simply harvest less than exists, and a
different amount each time. The inventory drifted 234 / 248 / 292 links across
runs before this was caught.

The fix is to compare each pass against `totalItems` — which the response has
been carrying all along — and re-walk until the count is reached.

**`rism_incipits.py` paginated identically.** Fixed there too, and re-run: three
consecutive runs now return the same 409 sources, which is exactly RISM's
`totalItems`. Completeness is verified rather than hoped for.

### The incipit corpus went 658 → 642 on scoring, then 642 → 620 on authorship

Porting the scoring filter to `rism_incipits.py` changed what counts as a quartet:

| | |
|---|---:|
| gained, scored `vl (2), vla, b` | **+4** |
| lost, scored `cemb (2)` — two harpsichords | −18 |
| lost, scored `vl (2), vla, vlc (2)` — a quintet | −2 |

The old filter's `^quartet` clause matched the **title**, so six keyboard-duo
arrangements titled "Quartets" were being counted as string quartets, and the
unanchored scoring pattern admitted a two-cello quintet. All 85 Gérard numbers
survive. **`build_page.py` needs re-running** — the published table was engraving
18 harpsichord incipits as quartet movements.

### Thirteen of the sources were Pleyel's

RISM's `/people/<id>/sources` returns every source a person is *related to*, in any role.
Pleyel dedicated his Op. 9 quartets to Boccherini, so those prints name him in a **`700`
with relator `$4 dte`** — dedicatee. The harvest read that as authorship.

**13 sources, all Pleyel**, all catalogued under `BenP` (Benton) rather than `GerB`, and
they had carried **22 Pleyel incipits** into the corpus plus **473 MB** of downloaded
facsimile — including a 79-page IIIF book whose own manifest label reads *"Pleyel, Ignaz:
Trois QUATUORS concertans"*. Four of the six RISM IIIF books in the inventory were Pleyel's.

Fixed with a `by_composer()` check in all four scripts: MARC **100** is the composer, so a
100 naming anyone else settles it.

| | before | after |
|---|---:|---:|
| incipits | 642 | **620** |
| incipits with no Gérard number | 23 | **1** |
| 856 links / sources | 292 / 181 | 279 / 176 |
| RISM IIIF books | 6 | **2** |
| unlinked holdings / libraries | 1463 / 169 | 1300 / 148 |
| Gérard numbers | 85 | 85 |

The tell was sitting in plain sight and I walked past it: **23 incipits with no Gérard
number**, in a corpus whose whole spine is the Gérard number. Twenty-two of those 23 were
Pleyel. A cluster of records that won't join your primary key is a provenance question, not
a data-quality footnote. The user spotted it from a title page.

### The filter bug that mattered most

The quartet filter was matching scoring `vl (2), vla, vlc` only. RISM spells the
same ensemble several ways — the bass is `vlc`, `b` or `bc`, the inner voice
`vla`, `t-vla`, `a-vla`, `violetta` or `taille`. **71 sources use
`vl (2), vla, b`**, and the narrow regex silently dropped **18 downloadable
digitizations**, including the only Biblioteca Nacional de España one. Widened,
with keyboard reductions (`cemb (2)`) and flute/piano quartets deliberately
still out. Fetchable links went 61 → 92.

### What a script cannot reach

Generated into `digitizations/MANUAL-DOWNLOADS.md` with a deep link, the shelfmark
and full metadata for each, because each reason was established by trying it:

- **7 Eichstätt manuscripts** behind an
  [Anubis](https://github.com/TecharoHQ/anubis) proof-of-work gate.
  `nbn-resolving.de` redirects to the same gated `.org` host. A browser solves it
  silently, so the links work when clicked.
- **1 Biblioteca Nacional de España** source — `bdh-rd.bne.es` accepts the TCP
  connection and then never completes the TLS handshake, so no request is ever
  sent. Reproducible against every BNE host tried. Worth retesting from your own
  network.
- **1 Manuscriptorium** record, which wants a portal session.
- **2 Staatsbibliothek Berlin records with nothing behind them.** SBB serves a
  valid manifest whose `canvases` list is *empty* — title and structure, no page
  images. Catalogued, not scanned. Reported rather than left as an empty folder.
- **1 Harvard link that is simply wrong.** RISM points at `drs:53358217`, which
  404s on Harvard's image server; the only thing the redirect chain yields is a
  manifest for **Campra's *L'Europe galante*, 284 pages**. A proxy denial
  happened to block it on the first run — otherwise someone else's ballet would
  have been filed under G 201 with no sign anything was amiss. Now refused
  outright, and every manifest's own label is recorded next to the images so a
  mismatch shows itself.

### RISM is a thin layer over what exists

**RISM links a scan for 71 of 1463 quartet holdings** — about 5%. The largest
holders have none at all: I-Nc (49 holdings), DK-Km (42), GB-Lbl (41),
B-Bc (38), S-Skma (32). `UNLINKED-HOLDINGS.md` is the worklist, by library,
largest first, with every shelfmark and RISM record.

**9 of those unlinked holdings are autographs**, which is where it bites. G 159
at D-Bhm (`RH 0322`) and G 171 at D-MÜs (`SANT Hs 531`), plus seven at the
Bibliothèque-Musée de l'Opéra under one shelfmark, `RES-507 (2)`. G 159 is the
same work whose two RISM records share nothing in common (below) — the autograph
that would settle it is catalogued and not linked.

### The autographs: found, and RISM's shelfmarks for them are wrong

`find_scans.py` searches the autograph libraries' own portals. Most of the
autograph holdings are at **F-Po**, which is a *département of the BnF* — so its
scans are on **Gallica**, which has an SRU API. Seven came back, every one
titled *autograph*, and all seven downloaded: **210 pages at 400 dpi**, into
`digitizations/found/BnF/`.

> **Superseded, 2026-09-28.** "Nine autograph holdings" was what the corpus could see
> at the time. Widening the quartet filter raised it to **31**, of which 19 are held —
> and revealed **ten more F-Po autographs** at `RES-507 (3)`–`(9)`, `(12)`, `(13)`, `(15)`
> that were never in the worklist. See *The `Quatuors` blind spot*, below.

They are the late quartets, dated by Boccherini himself:

| Gallica shelfmark | | pages |
|---|---|---:|
| RES-507 (2) | Opera Prima. 1781. Sei Quartettini | 104 |
| RES-507 (10) | La Tiranna. Mese di Agosto. 1792 | 16 |
| RES-507 (11) | Mese di Ottobre. 1792 | 18 |
| RES-507 (14) | Mese di Giugno. 1794 | 20 |
| RES-507 (16) | Mese di Agosto. 1794 | 16 |
| RES-507 (17) | Mese di Ottobre. 1794 (partly autograph) | 20 |
| RES-507 (18) | Mese di Decembre. 1794 | 16 |

**RISM gives all seven the shelfmark `RES-507 (2)`.** Only one of them is: the
*Sei Quartettini*, which is also the only record RISM titles "6 Quartets" rather
than "Quartets". The other six carry a sibling's shelfmark, and none of the seven
has a Gérard number. Gallica's metadata is the better record here — worth
reporting to RISM, and it makes the one-to-one identification tractable, which
is the next job.

I had written in the report that "Gallica's metadata carries no RISM shelfmark".
It does, in `dc:source`, and more precisely than RISM's own. Reading one record's
fields properly would have shown it.

The other two autographs — G 159 at D-Bhm `RH 0322` and G 171 at D-MÜs
`SANT Hs 531` — have no scriptable search. Münster's Visual Library serves OAI
but exposes no keyword endpoint, and the Universität der Künste has no IIIF
portal. Both are in the report with their RISM library page.

### How far recall actually goes

The first version of the Gallica search found 7 items. Pushing on recall took it to
**339 BnF-music Boccherini items, 37 of them string quartets**. Four things were
capping it, each measured rather than guessed:

| cap | effect |
|---|---|
| `maximumRecords=50`, no pagination | saw 50 of **2515** matching records |
| Gallica drops a page silently | `startRecord=101` returned 0 records, no error |
| only autograph libraries were searched | **40 of 47** BnF holdings never queried |
| title filter demanded "quartet"/"quatuor" | missed *Divertimenti*, *Sonatas* |

Gallica has **exactly the same silent-pagination fault as RISM**, so the walk retries
an empty page before believing it.

**Recall for quartets is now saturated.** Raising the walk from 400 to 1200 records
found 31 more BnF items and **zero** more string quartets.

**What that yielded: 39 items, 1948 pages, 4.2 GB in `digitizations/found/BnF/`**, every
one verified against its manifest. The single largest is an autograph that only the
`Divertimenti` search term reached — *"1773. Opera Prima. Divertimento Primo, per due
Violini…"*, 335 pages — followed by *"Opera I. 1777. Sei Quartetti"* (`MS-1292`, 118 pp.,
autograph), which the earlier over-strict scoring test had thrown away.

Two items classified `quartet?` are reported as inferences and one of them is a visible
false positive: *"Sinfonia a grande orchestra, con due Violini Principali"* is not a
string quartet, whatever its four-part scoring says. Maximising recall buys that, which
is why the form is labelled rather than asserted.

**Variant spellings turned out not to matter.** RISM's own MARC attests `Bocherini`
(46), `Boccarini` (8), `Boccherinj` (6), `Boccharini` (2), `Bucherini`. Querying each
added no quartets, because Gallica's SRU `all` operator is already fuzzy —
`Bocquerini`, a spelling I invented, returns 2396 records. Attested variants would
matter at a portal doing exact matching; they do nothing here.

**The title vocabulary that does matter**, counted in RISM's 613 full titles:
`quartetto` (243), `quartettino`/`quartettini` (113), `quartetti` (69),
`quatuor(s)` (83), `divertimento`/`Divertimentos` (19), `quarteto` with one t (7),
and `Sonatas` — RISM's uniform title for 7 of these quartets. Nothing for notturni,
conversazioni or trattenimenti, which is worth knowing too.

Items titled *Sonata* or *Sinfonia* are classified `quartet?` and only when the title
spells out four string parts; they are downloaded but reported separately, because the
form is an inference. Quintets (59), trios (8) and unclassified items are listed
rather than dropped, and arrangements are excluded on a *named* wind or keyboard part —
which keeps the flute and clarinet reductions out while keeping in autographs whose
titles simply never state a scoring.

### Which libraries can be searched at all

`survey_portals.py` gives all **169** libraries a verdict with its evidence: holdings
count, the library's own website (RISM stores it at `location.website`), every host
RISM already links for it, and whether OAI-PMH or SRU answers there.

| verdict | libraries | holdings |
|---|---:|---:|
| `known` — tried by hand; works, or actively refuses | 15 | 293 |
| `api` — OAI or SRU answered | 2 | 45 |
| `website` — a site to search, no API at the usual paths | 129 | 1047 |
| `no url` — RISM records no website and links no host | 23 | 78 |

Two caveats that matter more than the table. **Probe yield is terrible — 1 host in 21
answered** — because a library's public website is almost never its catalogue server,
and the catalogue sits on a subdomain no convention predicts. And probing is
incomplete: it runs in a sandbox that needs every host declared up front, and
redirects keep introducing new ones. Probe results cache to `.rism-cache/portals.json`,
so finishing it outside the sandbox repeats no work. Treat `website` as "nothing at
the conventional paths", not "impossible".

One incidental find: **RISM's own Muscat platform exposes SRU** at
`muscat.rism.info/sru`, and it rejects `version=1.2` as "Unsupported version" — it
wants **1.1**. 320 records for Boccherini, fewer than the JSON API returns, so it is a
curiosity rather than a better source.

### Holdings count does not predict digitization — twice burned

Two libraries were chosen as next targets on the strength of their RISM holdings and their
digitization reputation. Both were dead ends, and one search each settled it:

| library | RISM holdings | actually online |
|---|---:|---|
| S-Skma | 34 | 4 digitized; the one downloaded is a print RISM calls a manuscript |
| D-Mbs | 34 | 2 Boccherini manuscripts, **both quintets** |

Munich was recommended because BSB digitizes aggressively *and* its delivery API is
scriptable from here — both true, and both beside the point, because they have not digitized
Boccherini quartets. A holdings count counts catalogue entries. The first move at any library
is a one-minute search for what is actually online; it beats any amount of reasoning from
holdings.

### musiconn.search is RISM again, not a new layer

A saved musiconn.search page resolved to `opac.rism.info`, Berlin, Rochester, Eichstätt, MDZ
and SLUB — the same MARC 856 links `rism_digitizations.py` already harvests. **60 of its 65
digitization links were already held.** Of the five left: one was the Pleyel print, one the
Manuscriptorium item already downloaded by hand, one a Frankfurt URN behind the Anubis gate,
and two were Dresden's `Mus.3490-P-10a/b` — which SLUB labels "3 Quartets" but which are
scored `cemb (2)`, the harpsichord-duo arrangement whose 18 incipits the scoring filter had
already removed. A federated search over RISM returns RISM.

I did **not** build general per-library portal search beyond that survey. Search endpoints were tested and
are inconsistent: Frankfurt exposes OAI, the Italian SBN catalogue returns
scrapable HTML, Copenhagen 403s, Dresden's and the British Library's endpoints
refused outright. A generated search URL per library would mostly be a guess, so
each institution gets its RISM library page instead, which lists its holdings
and its own catalogue link.

**Bodleian holds no Boccherini string quartets at all** in RISM — worth knowing
before searching it. E-Mn has 12 holdings, E-Mp 2.

---

## Duplicate incipits: what the disagreements actually are

Most movements are encoded more than once — **134 of 182** (work, movement)
groups. Only 12 of those are explained by different instruments. Narrowing to
the same work, movement **and part**, there are **128** groups with two or
more records:

| | groups | |
|---|---:|---:|
| identical notes | 17 | 13% |
| one is a **prefix** of another — just a longer incipit | 36 | 28% |
| **genuinely divergent** | 75 | 59% |

So 41% resolves mechanically: take the longest. The other 75 break down as:

| | |
|---|---:|
| different notes | 56 |
| rhythm only | 15 |
| octave only | 3 |
| accidental only | 1 |

### How much they differ

Worst-disagreeing pair per group, over their common span:

| differing notes | different notes | rhythm only |
|---:|---:|---:|
| 1 | 6 | 3 |
| 2 | 4 | 6 |
| 3 | 0 | 1 |
| 4–5 | 6 | 1 |
| 6–10 | 6 | 1 |
| **11+** | **34** | 3 |

| first difference at note | different notes | rhythm only |
|---:|---:|---:|
| **0 (the very first)** | **30** | 1 |
| 1–2 | 7 | 4 |
| 3–5 | 10 | 2 |
| 6–10 | 5 | 4 |
| 11+ | 4 | 4 |

| share of common span differing | median | min | max |
|---|---:|---:|---:|
| different notes | **90%** | 5% | 100% |
| rhythm only | 14% | 5% | 80% |

### The conclusion: two different problems

It is **bimodal, not a spectrum.**

**The large cluster is not variant readings — it is mismatched records.** 34 of
56 differ in 11+ notes, 30 differ from the very first note, and the median is
90% of the span. Two transcriptions of the same music do not diverge at note
one and stay divergent. Spot-checking the 25 worst (>80% differing),
**17 carry different tempo captions** — `Allegretto` vs `Allegro non tanto`,
`None` vs `Comodo` — and one pair disagrees on key (`c` vs `E♭`). These are
different movements or different works sharing a Gérard number and movement
slot. Example: G 159 movement 1 for cello has two records with nothing in
common —
[650004088](https://rism.online/sources/650004088) vs
[1001054992](https://rism.online/sources/1001054992).

**The genuinely fixable set is small: ~23 groups differ in only 1–2 notes.**
Those, plus the 4 octave/accidental-only cases, have the profile of
transcription slips and are worth reporting to RISM.

### Picking the best reading

1. Longest wins — resolves the 28% prefix cases outright.
2. Then most sources agreeing, then the most authoritative siglum.
3. Flag rhythm / octave / accidental-only disagreements as probable slips.
4. **Do not try to merge the wholesale-different ones.** Check why two records
   are attached to the same work instead; a heuristic will just pick one of
   two unrelated pieces.

---

## Contributing incipits back to RISM

RISM has a real route, but it is institutional rather than a pull request.

- **Muscat** is RISM's open-source cataloguing platform and the way records are
  created or edited. A login is tied to the institution(s) you are authorised
  to edit, so contribution normally runs through a library, archive or a
  national RISM working group.
- **Contact `contact@rism.info`** (RISM Editorial Network) about using Muscat
  or contributing records. Technical questions: Rodolfo Zitellini,
  `rodolfo.zitellini@rism.digital`.
- **Without edit privileges you can still add a comment to a record**, which
  flags it for Zentralredaktion staff. That is the low-friction path for
  "here is a missing incipit" or "this one is wrong".
- RISM explicitly **expects people who download incipit data to report
  corrections back**, so this is the thing they ask for, not an imposition.
- Read the [cataloguing guidelines](https://guidelines.rism.info/) first —
  they cover when to create a new record versus amend one, and there is a
  video on encoding incipits in P&E. RISM did ~156,000 incipit corrections in
  a recent cleanup, so consistency matters to them.

Op. 58 has **zero** incipits in RISM and you have the parts — that is the
clearest contribution available.

---

## Verification

`--check` round-trips all 658 through MusicXML and back via two readers:

```
read back by       exact  differs  rejected     trills   catches
Verovio              658        0         0    181/181   semantics; blind to beaming
from_musicxml        658        0         0    181/181   notation: beams, tuplets, grace groups
```

Both are needed. Verovio regenerates beaming on import, so it cannot see a
broken beam chain — one shipped for days behind a green Verovio check.

Independently: music21, which drops *every* trill reading Verovio's MEI, reads
this MusicXML with 181/181 trills and 337/337 grace notes intact.

---

## Corrections — things I asserted and had to retract

Recorded because the pattern matters more than the items.

- **Verovio *can* write P&E** (`renderToPAE`, including from MusicXML input).
  I said it couldn't, having grepped its methods for "MIDI" only. A `dir()`
  would have settled it in one call.
- **The "dangling fermata" was our bug**, not Verovio's. The `startid` pointed
  at a `<rest>`, which the reader didn't index — so the reference looked
  dangling and the fermata was dropped. Two fermatas were being silently lost.
  Fixed. I was one command away from filing it against someone else's project.
- **Our ABC writer did not beat `xml2abc`.** I reported 197 vs 146; the test
  had an `if False else` typo that stripped ornaments from one side only.
  Stripped from both: **197/200 each — a dead tie.**
- **~40% of the converter duplicated existing tools.** The landscape research
  happened *after* building rather than before.
- **I reported the digitization inventory three times with three different
  numbers** — 248, then 292, then 234 links — and read the variation as my own
  filter changing, because I never compared any of them against the `totalItems`
  the response was handing me. It was RISM's pagination dropping records. A count
  that moves between identical runs is the finding, not a detail.
- **"Only `vl (2), vla, vlc` is a quartet"** — asserted by writing the regex that
  way and never checking what other scorings existed. One `value_counts` over the
  corpus would have shown 71 sources spelled `vl (2), vla, b`.
- **I treated "sources for this person" as "works by this person"** for the whole
  project, and downloaded 473 MB of Ignaz Pleyel on the strength of it. RISM was not
  wrong; `$4 dte` says dedicatee plainly. I never looked at MARC 100. The signal I had
  and ignored: 23 incipits carrying no Gérard number in a corpus keyed on Gérard numbers.

The durable lesson: **verify with a reader you didn't write.** Every real bug
here surfaced that way, and every wrong claim came from skipping it.

---

## Use the tool that exists

Measured head to head, each of these matched a hand-written equivalent
exactly, so writing your own buys nothing:

| need | use |
|---|---|
| → Plaine & Easie | Verovio `renderToPAE()` (mind the `@data:` newline) |
| → LilyPond | `musicxml2ly` |
| → ABC | `xml2abc` — <https://wim.vree.org/svgParse/> |
| ABC → | `abc2xml`, same author. Keeps barlines; music21 re-bars |
| checking ABC | `abc2midi` — never an ABC *importer* |
| → MusicXML | nothing else does it. That's `incipit_convert.py` |

---

## Environment notes

- `musicxml2ly` was broken: Homebrew's `python@3.14` ships a `pyexpat` linked
  against `/usr/lib/libexpat.1.dylib`, which lacks
  `XML_SetAllocTrackerActivationThreshold`. A shim at
  `~/.local/bin/musicxml2ly` runs it under Apple's Python instead. It prefers
  the original interpreter and falls back only while that one is broken, so it
  retires itself once Homebrew ships a fix. Check with:
  `/opt/homebrew/opt/python@3.14/libexec/bin/python -c 'import pyexpat'` —
  if that stops erroring, `rm ~/.local/bin/musicxml2ly`.
  Ten other Homebrew scripts share that interpreter; copy the shim under their
  names if you hit one.
- Installed for ABC work: `brew install abcmidi abcm2ps`.
- `abc2xml` / `xml2abc` are **not** vendored — they live in a temp dir and are
  not on PyPI. Re-download from <https://wim.vree.org/svgParse/> if needed.

---

## Sidecars were being overwritten on every harvest — 2026-09-28

The harvester rebuilt `metadata.json` from RISM and **wrote it out whole**, discarding every
field added afterwards. That is the single cause behind most of the linkage confusion in
this project: enrichment appeared to work, then quietly vanished on the next `--download`,
and reappeared only when someone happened to re-run the script that produced it.

What it was deleting: the publisher parsed from a title imprint, the normalised
`rism_related`, and `page_index` — the record of what the page filenames encoded before the
images were moved to Trash. `check_archive.py` caught 42 folders missing their page index
within minutes of being written.

`write_sidecar()` now merges: keys this run produces win, everything else is carried over.

**The folder name is still rebuilt from RISM.** A Gérard number established by looking at a
scan must go in `corrections.json`, or `relocate()` will move the folder back.

## RISM numbers an anthology as a whole — 2026-09-28

Pleyel's twelve-quartet *œuvre 39* is one RISM record, **990005884**, carrying a **single**
Gérard number, G 234. Our folders carry the livraison's own numbers, established by hand.
So the work-level join — which matched on an exact Gérard set — could not reach any of the
ten œuvre 39 folders, and they showed as "not in RISM" when the record was sitting right
there.

Two further traps in the title fallback that replaced it:

- On words alone the Library of Congress Op. 54 matched a Naples manuscript of **G 165**.
  Boccherini's title pages are formulaic — *"Tre quartetti per due Violini, Viola e Basso"*
  fits a dozen unrelated sources. A title match needs a shared opus number to mean anything.
- The number guard then did nothing, because the tokeniser had a 3-character floor and
  **`39` is two characters**. It now reads numbers off the raw title.

"Not in RISM" went 50 → 14 → **4**, and the four are one genuine absence (Op. 54, no GerB
above 249 exists) and three things that are not quartets.

## The `Quatuors` blind spot — 2026-09-28

`is_quartet()` decides on RISM's scoring field, and falls back to the uniform title when a
record gives no scoring. The fallback regex only knew the English `quartet`. Among the
scoring-less records, **`Quatuors` outnumbers `Quartets` two to one**, so the fallback
silently dropped the entire BnF manuscript holding — including **ten F-Po autographs**.

Fixed by matching `quartet|quatuor|quartett`, with two guards: the fallback now also
demands a Gérard number, and drops titles that name a single movement — unless the source
is an autograph, which is kept regardless.

| | before | after |
|---|---:|---:|
| incipits | 620 | **643** |
| unlinked holdings tracked | 1300 | **1344** |
| autograph holdings known | 9 | **31** |
| autographs still open | 2 | **12** |

The "autographs still open" number going **up** is the point: it was wrong before, not
better. Ten F-Po autographs existed and were invisible.

## The identification pass — 2026-09-28

33 folders held images with no Gérard number. `suggest_ids.py` scores three independent
signals — shelfmark join against RISM, rare-word title overlap, and the publisher's
`libro` number — and writes `digitizations/TO-IDENTIFY.md`.

Shelfmark alone resolved one. What resolved the rest is that Gallica's titles often state
the answer outright: *"Y. Gérard 168"*, *"Oeuvre 39 [3ème] livraison"*, *"Opera XI. Libro
quarto"*. The `libro primo`–`quinto` series maps onto Gérard and is corroborated by RISM
records that carry GerB numbers, so it can be trusted rather than guessed.

**30 identified, 3 marked not-a-quartet, 0 left.**

Two side findings: **Op. 58 is at Paris as well as Berlin** (`VM7-1308 (1)` and `(2)`),
which the project had believed was Berlin-only; and one real duplicate, `btv1b90663033`,
the same Gallica ark and identical images as `G201-206/990005880_F-Pc`.

## Hand edits to folder metadata do not survive

Twice now, an identification written into a folder's `metadata.json` was silently reverted:
the harvester rebuilds folder names and metadata from RISM on every run, and `relocate()`
moves the folder back. Both cases were records RISM gives no Gérard number — D-B `KHM 577`
and the D-LEm volume.

Anything established by looking at a scan belongs in **`corrections.json`**, keyed by RISM
source id. Nowhere else.

---

## Open

- [ ] File the Verovio issue — <https://github.com/rism-digital/verovio/issues/new>
- [ ] Decide on `incipit_convert.py`: publish narrow (a tested MEI → MusicXML
      converter plus the round-trip harness) or keep it local
- [ ] Vendor `abc2xml` / `xml2abc` if the ABC path matters
- [ ] Consider a PR documenting the four P&E gotchas
- [ ] **Get the ten F-Po autographs** — `RES-507 (3)`–`(9)`, `(12)`, `(13)`, `(15)`, the
      monthly *quartettini* of 1789–1794. Every neighbouring number in that run is already
      on Gallica, so these are probably downloadable, not letter-writing targets
- [ ] **Tell RISM its F-Po shelfmarks are wrong** — seven records all read `RES-507 (2)`;
      only one is. The correct numbers are now known and recorded in `found/BnF/`
- [ ] Order D-MÜs `SANT Hs 531` (G 171) — `digitizations/MUENSTER-REQUEST.md` is drafted.
      The only remaining autograph candidate genuinely contemporary with Boccherini
- [ ] Send `digitizations/STAMS-REQUEST.md` — nine A-ST manuscripts
- [ ] Report the ~23 one-or-two-note disagreements to RISM (likely slips)
- [ ] Investigate the ~34 wholesale-different pairs — these look like records
      attached to the wrong work, not variant readings
- [ ] Ask the 5 biggest unlinked holders (I-Nc, DK-Km, GB-Lbl, B-Bc, S-Skma)
      whether scans exist; 202 quartet holdings sit behind those five sigla
- [ ] Decide whether to order D-B `KHM 571`–`576` — Op. 32 **in score**, one quartet per
      volume. Not a duplicate of the `KHM 577` part-set we hold; we have no Op. 32 score

### Closed on 2026-09-28

- [x] Re-run `build_page.py` and republish — now the 643-incipit corpus (version 5)
- [x] Publish the sources shelf — <https://claude.ai/artifact/YbGE1XtRkKt26BQahVtgMH>
- [x] Identify the F-Po autographs against Gérard numbers — all ten, plus the seven held
- [x] Identify everything in `digitizations/unidentified/` — 0 remain
- [x] Work `MANUAL-DOWNLOADS.md` by hand — BNE is complete, 12 filed, 2 skipped
- [x] BNE resolver — unnecessary in the end; every BNE item was fetched by hand
- [x] Op. 58 has no incipits in RISM — **confirmed genuinely absent**, not a harvest gap.
      990005886 is the only Op. 58 source RISM holds and it carries none. See
      `digitizations/OPUS-58-AND-CARMIRELLI.md`
