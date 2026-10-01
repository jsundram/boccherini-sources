# Verovio issue — ready to file

**File it here:** <https://github.com/rism-digital/verovio/issues/new>

**Suggested labels:** `plaine and easie`, `bug`

**Duplicate check (done):** searched `rism-digital/verovio` for *PAE output*,
*PAE tie startid*, *plaine easie tie*. The only near neighbour is
[#3632 — "Newline missing at end of PAE conversions"](https://github.com/rism-digital/verovio/issues/3632)
(closed, low priority), which is about a missing newline at the **end** of the
output. This is a different newline, in a different place, with a much worse
consequence.

**Verified against:** verovio 6.3.0-425dd7b, Python bindings (`pip install verovio`).

---

Everything below the line is the issue body — copy it as-is.

---

## Title

`renderToPAE()` output cannot be read back by Verovio's own PAE parser (silently yields an empty score)

## Body

### Summary

`renderToPAE()` writes `@data:` followed by a newline, putting the music on the
next line. Feeding that output straight back into `loadData()` with
`inputFrom: "pae"` produces an **empty score** — and `loadData()` returns
`True`, so nothing signals that anything went wrong.

Joining `@data:` to the music on a single line makes it round-trip perfectly,
so the content is right; only the framing is.

### Steps to reproduce

```python
import verovio

tk = verovio.toolkit()
tk.setOptions({"inputFrom": "pae"})
tk.loadData("@clef:G-2\n@timesig:4/4\n@data:4C4D4E")

out = tk.renderToPAE()
print(repr(out))
# "@timesig:4/4\n@clef:G-2\n@data:\n'4CDE"
#                            ^^ newline after @data:

t2 = verovio.toolkit()
t2.setOptions({"inputFrom": "pae"})

print(t2.loadData(out))            # True   <- reports success
print(t2.getMEI().count("<note"))  # 0      <- but there are no notes

fixed = out.replace("@data:\n", "@data:")
print(t2.loadData(fixed))          # True
print(t2.getMEI().count("<note"))  # 3      <- correct
```

### Expected

Any one of these would fix it:

1. `renderToPAE()` emits `@data:` and the music on one line, so its own output
   is valid input to Verovio's PAE parser; or
2. the PAE parser accepts a newline after `@data:` — the `@keyword:` form
   suggests a value could legitimately continue on the next line; or
3. `loadData()` returns `False` when it parses input into an empty score.

(3) seems worth doing regardless of (1)/(2). The silent success is what makes
this expensive: a pipeline that round-trips through PAE loses every score and
reports no error anywhere.

### Actual

`loadData()` returns `True`; the resulting MEI contains no `<note>`, `<rest>`
or `<measure>` content.

### Impact

Verovio both reads and writes Plaine & Easie, so using it for both ends of a
PAE round trip is the natural thing to do — and it silently discards
everything. Found while round-tripping RISM's Boccherini incipits; reproduces
on the three-note example above.

### Notes

- Also reproduces when the score was loaded from MusicXML
  (`inputFrom: "musicxml"`, then `renderToPAE()`), so it is in the PAE
  writer/reader pair rather than the PAE importer.
- Environment: verovio 6.3.0-425dd7b, Python 3.14, macOS arm64.

---

## Not filed: a second bug that turned out to be ours

An earlier draft also reported Verovio emitting `<fermata>` elements whose
`startid` pointed at no element in the document.

**That was our bug, not Verovio's.** The `startid` pointed at a `<rest>`, and
our reader only indexed `<note>` and `<chord>`, so the reference looked
dangling and the fermata was dropped. Plaine & Easie writes `(-)` for a
fermata on a rest, and Verovio encodes it correctly.

Checked across all 658 incipits: every `startid` resolves to an element
present in the MEI. Fixed on our side by indexing rests — two fermatas that
had been silently dropped are now preserved.

Recorded here as a reminder to establish which side of the boundary a bug is
on before filing it against someone else's project.
