# /// script
# requires-python = ">=3.11"
# dependencies = ["verovio", "pytest"]
# ///
"""Fast tests for incipit_convert -- no corpus required.

    uv run --with pytest pytest test_incipit_convert.py -q

`incipit_convert.py --check` is the integration test: it runs the whole RISM
corpus through to_musicxml and back, via both Verovio and from_musicxml. It is
the real safety net, but it needs a 320KB data file. These tests need neither,
and they pin the behaviours that were expensive to discover -- each one cost a
debugging session, and several are undocumented quirks of Plaine & Easie that
no amount of spec reading would have surfaced.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import incipit_convert as C  # noqa: E402


# --------------------------------------------------------------- helpers

@pytest.fixture(scope='session')
def tk():
    return C.engraver()


def pae(data, clef='G-2', keysig=None, timesig='4/4'):
    head = [f'@clef:{clef}']
    if keysig:
        head.append(f'@keysig:{keysig}')
    head += [f'@timesig:{timesig}', f'@data:{data}']
    return '\n'.join(head)


def model(tk, data, **kw):
    return C.parse_mei(C.pae_to_mei(tk, pae(data, **kw)))


def notes(inc):
    """(pname, sounding alter, octave, duration, is-grace) per note."""
    return C.note_stream(inc)


def roundtrip_mxl(inc):
    return C.from_musicxml(C.to_musicxml(inc))


# --------------------------------------------------------------- P&E quirks
# Each of these is a rule the Plaine & Easie spec does not make obvious, and
# each one silently corrupted output before it was found.

def test_trill_attaches_to_preceding_note(tk):
    """`4Ct` trills C. `4tC` is silently IGNORED -- no trill at all."""
    assert C.ornaments(model(tk, '4Ct4D'))[0] == 1
    assert C.ornaments(model(tk, '4tC4D'))[0] == 0


def test_r_terminates_a_grace_group(tk):
    """Without the closing `r`, a grace group swallows the rest of the bar."""
    closed = notes(model(tk, 'qq3{CDE}r2D'))
    open_ = notes(model(tk, 'qq3{CDE}2D'))
    assert [n[4] for n in closed] == [True, True, True, False]
    assert all(n[4] for n in open_), 'unterminated group should absorb the D'


def test_parens_are_fermata_on_one_note_tuplet_on_a_group(tk):
    """`(X)` is a fermata; `(XYZ)` is a tuplet. Disambiguated by count."""
    assert C.ornaments(model(tk, '4C(D)4E'))[1] == 1        # fermatas
    trip = notes(model(tk, '(8CDE)'))
    assert len(trip) == 3 and all(n[3] == C.Fraction(1, 12) for n in trip)


def test_tuplet_ratio_defaults_to_three(tk):
    """A bare group is a TRIPLET. `;N` states any other count -- but the
    denominator is always 2, so `;7:4` still reads back as 7:2."""
    assert notes(model(tk, '(8CDE)'))[0][3] == C.Fraction(1, 12)
    six = notes(model(tk, '(8CDEFGA;6)'))
    assert len(six) == 6 and six[0][3] == C.Fraction(1, 24)
    bare = notes(model(tk, '(8CDEFGA)'))
    assert bare[0][3] == C.Fraction(1, 12), 'bare sextuplet is read as a triplet'


def test_octave_and_duration_are_sticky(tk):
    """A note's octave and duration live in the stream, not the note."""
    n = notes(model(tk, "''4CDE"))
    assert [x[2] for x in n] == [5, 5, 5]
    assert [x[3] for x in n] == [C.Fraction(1, 4)] * 3


def test_chord_moves_the_sticky_octave(tk):
    """The note after a chord inherits the LAST chord tone's octave."""
    n = notes(model(tk, "'4C^,G4E"))
    assert n[0][2] == 4 and n[1][2] == 3
    assert n[2][2] == 3, 'E follows the chord, so it sits in the lower octave'


# --------------------------------------------------------------- writers

@pytest.mark.parametrize('data,kw', [
    ("{''8B6.F3D}{'BF}4D6-{''BAG}/{nEFDF}", {}),   # a real RISM incipit
    ('4C4D4E4F', {}),
    ('{8CD}{8EF}', {}),
    ('(8CDE)4F', {}),
    ('q8C4D', {}),
    ('qq3{CDE}r4D', {}),
    ('4C+4C', {}),
    ('4Ct4D', {}),
    ('4C(D)', {}),
    ("4C^E^G", {}),
    ('4C4-4D', {}),
    ('{8C6-D}', {}),                               # rest inside a beam
    ('(8-CD)', {}),                                # tuplet starting on a rest
    ('{(8CDE;3)}', {}),                            # beam outside tuplet
    ('4xC4bD4nE', {}),
    ("4,,C4,C4C4'C4''C", {}),
    ('4C4D', {'keysig': 'bBE'}),
    ('4C4D', {'keysig': 'xFC'}),
    ('4C4D', {'clef': 'F-4'}),
    ('4C4D', {'clef': 'C-3'}),
    ('4C4D', {'timesig': 'c'}),
    ('4C4D', {'timesig': 'c/'}),
    ('4C4D4E', {'timesig': '6/8'}),
])
def test_musicxml_roundtrip_preserves_everything(tk, data, kw):
    """The main contract: nothing is lost writing MusicXML and reading it back."""
    a = model(tk, data, **kw)
    b = roundtrip_mxl(a)
    assert notes(a) == notes(b)
    assert C.ornaments(a) == C.ornaments(b)
    assert a.fifths == b.fifths and a.clef == b.clef


@pytest.mark.parametrize('data', [
    '4C4D4E', '{8CD}{8EF}', '(8CDE)4F', 'q8C4D', 'qq3{CDE}r4D',
    '4C+4C', '4Ct4D', '4C(D)', '4C^E^G', '4C4-4D',
    '{8C6-D}', '(8-CD)', '{(8CDE;3)}', '(8CDEFGA;6)',
])
def test_musicxml_roundtrip_preserves_music(tk, data):
    a = model(tk, data)
    b = roundtrip_mxl(a)
    assert notes(a) == notes(b)
    assert C.ornaments(a) == C.ornaments(b)


def test_rest_inside_beam_keeps_the_beam_closed(tk):
    """Rests carry no beam markers, so they must be transparent to the
    begin/end chain -- otherwise beams never close and nest into each other."""
    a = model(tk, '{8C6-D}{8E6-F}')
    xml = C.to_musicxml(a)
    beams = [ln for ln in xml.splitlines() if '<beam' in ln]
    assert sum('begin' in b for b in beams) == sum('end' in b for b in beams) > 0
    assert notes(a) == notes(roundtrip_mxl(a))


def test_beam_inside_tuplet_closes_innermost_first(tk):
    """Both end on the same note; popping only the outer leaves the tuplet
    open and every later note inherits its ratio."""
    a = model(tk, '4C(6-{DEF};3)4G')
    b = roundtrip_mxl(a)
    assert notes(a) == notes(b)
    assert notes(b)[-1][3] == C.Fraction(1, 4), 'the G must escape the tuplet'


def test_grace_group_is_rebuilt_from_musicxml(tk):
    """MusicXML has no grace GROUP, only consecutive grace notes -- so a run of
    them is regrouped on the way back, or one turn figure becomes several
    separate appoggiaturas."""
    a = model(tk, 'qq3{CDE}r4D')
    b = roundtrip_mxl(a)
    grps = [e for m in b.measures for e in m.events
            if isinstance(e, C.Group) and e.kind == 'graceGrp']
    assert len(grps) == 1
    assert notes(a) == notes(b)


def test_grace_notes_carry_no_musicxml_duration(tk):
    """A <grace> note with a <duration> is invalid MusicXML."""
    xml = C.to_musicxml(model(tk, 'q8C4D'))
    for chunk in xml.split('<note>')[1:]:
        if '<grace' in chunk:
            assert '<duration>' not in chunk


def test_convert_end_to_end(tk):
    xml = C.convert(pae("''4GAg8C'4nB{8.D3EF}(8CDE)4C+4C"), tk=tk)
    assert xml.startswith('<?xml') and '<score-partwise' in xml


# --------------------------------------------------------------- refusals
# The module must fail loudly rather than degrade silently.

def test_foreign_tuplet_survives_musicxml():
    """MusicXML can hold any ratio, unlike P&E, where tuplets are always
    N-in-the-space-of-2. Nothing should be refused on the way out."""
    inc = C.Incipit(clef=('G', '2'), fifths=0, meter=('4', '4', None))
    g = C.Group(kind='tuplet', num=5, numbase=4,
                children=[C.Note(pname='c', oct=4, dur='8') for _ in range(5)])
    inc.measures.append(C.Measure(events=[g]))
    back = C.from_musicxml(C.to_musicxml(inc))
    assert notes(inc) == notes(back)


def test_unknown_duration_is_refused():
    with pytest.raises(C.Unsupported):
        C.from_musicxml(
            '<score-partwise><part id="P1"><measure number="1">'
            '<note><pitch><step>C</step><octave>4</octave></pitch>'
            '<type>hemidemisemiquaver</type></note></measure></part></score-partwise>')


def test_non_partwise_musicxml_is_refused():
    with pytest.raises(C.Unsupported):
        C.from_musicxml('<score-timewise></score-timewise>')


# --------------------------------------------------------------- upstream quirks

def test_verovio_pae_output_needs_data_on_one_line(tk):
    """REGRESSION GUARD, not our bug: Verovio's renderToPAE emits `@data:` then
    a NEWLINE, and Verovio's own P&E reader then yields an empty score while
    loadData() still returns True. Anything consuming renderToPAE must join
    that line first. Delete this test if Verovio fixes it."""
    tk.loadData(pae('4C4D4E'))
    out = tk.renderToPAE()
    assert '@data:\n' in out

    t2 = C.engraver()
    assert t2.loadData(out) is True, 'the silent part: it reports success'
    assert len(notes(C.parse_mei(t2.getMEI()))) == 0, 'but parses nothing'

    assert t2.loadData(out.replace('@data:\n', '@data:'))
    assert len(notes(C.parse_mei(t2.getMEI()))) == 3
