# Op. 58 (G 242–247), and where Pina Carmirelli fits

## The short answer on the Ricordi edition

**The 1961 Ricordi edition is not in RISM, and never will be.** RISM catalogues manuscripts
and early printed sources; it does not index modern editions. Every record in this corpus
dated after 1850 is a *manuscript*, not a print — there is no exception to link to.

So a copy of the Ricordi print cannot be joined to a RISM source record, because no such
record exists. That is a fact about RISM's scope, not a gap in our data.

## But RISM does have Carmirelli — 53 sources

She is in RISM as a **scribe**, not as an editor. At **I-Mcv**, Biblioteca della Casa di
riposo per musicisti (Casa Verdi, Milan), RISM records 53 Boccherini sources whose notes read

> *Copie autografe di Pina Carmirelli con indicazioni di esecuzione e diteggiature*

— her own manuscript copies, carrying her performance markings and fingerings, tagged
`700 $a Carmirelli, Pina $4 scr`. Dated `[1940-1960]`, which is exactly the period of the
work behind the Ricordi edition.

Most are quintets. **Seven are quartets:**

| Gérard | RISM | what it is |
|---|---|---|
| **243** | [850792996](https://rism.online/sources/850792996) | *2. quartetto in mi b magg.* — **Op. 58 no. 2**, 4 parts (7, 6, 6, 6 p.) |
| 248 | [850792997](https://rism.online/sources/850792997) | Op. 64 no. 1, 4 parts |
| 249 | [850793005](https://rism.online/sources/850793005) | first movement only of Op. 64 no. 2 |
| 206 | [850793040](https://rism.online/sources/850793040) | Op. 32 no. 6, 4 parts |
| 213 | [850793044](https://rism.online/sources/850793044) | score + parts |
| 214 | [850793049](https://rism.online/sources/850793049) | 4 parts |
| 172 | [850793215](https://rism.online/sources/850793215) | parts for **fl**, vl, vla, vlc |

**Exactly one is Op. 58** — G 243, no. 2. None is digitized, and RISM links no scan for any
of the 53.

## How to file the Ricordi copies

There is no source record, so they attach to the **work**, the way the Library of Congress
Op. 64 does. Use:

- `rism_related` → [990005886](https://rism.online/sources/990005886), the `[1803c]` print,
  which is the **only** Op. 58 source RISM holds at all
- `rism_catalogues_this_copy: false`, with the reason
- `medium: "modern edition"`, `editor: "Pina Carmirelli"`, `publisher: "Ricordi"`,
  `publication_place: "Milano"`, `year: "1961"`
- a pointer to [850792996](https://rism.online/sources/850792996), Carmirelli's own manuscript
  of Op. 58 no. 2, as the editorial provenance behind the print

Drop them in `digitizations/G242-247/ricordi-1961-carmirelli/` and they will appear on the
shelf like everything else.

## What Op. 58 looks like on disk now

Op. 58 was thought to be Berlin-only. It is not — the Paris copies turned up in the Gallica
finds and have just been identified:

| folder | siglum | shelfmark | note |
|---|---|---|---|
| `G242-247/990005886_D-B` | D-B | `DMS 51778` | |
| `G242-247/990005886_D-B_livr1` | D-B | `DMS 51778` | livraison 1 |
| `G242-247/990005886_D-B_livr2` | D-B | `DMS 51778` | livraison 2 |
| `G242-247/990005886_US-R` | US-R | — | 4 parts |
| `found/BnF/btv1b108778048` | F-Pn | `VM7-1308 (1)` | *Op. 58. 1re partie* — only 15 images |
| `found/BnF/btv1b10877805q` | F-Pn | `VM7-1308 (2)` | *Op. 58. 2e partie* — 88 images |

**Unresolved:** which three quartets each *partie* contains. The title says *"en deux
livraisons"*, so presumably 242–244 and 245–247, but that is an inference and the 15-image
first part looks like a single part-book rather than three quartets in four parts. Both
folders are filed as G 242–247 with that stated in `gerard_established_by`.

Op. 58 still has **zero incipits in RISM** — 990005886 carries none, which is why it never
appeared in the incipit corpus.
