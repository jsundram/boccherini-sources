# /// script
# requires-python = ">=3.11"
# dependencies = ["verovio"]
# ///
"""Plaine & Easie (or any MEI) -> MusicXML.

    uv run tools/mei/incipit_convert.py --check                  # round-trip the corpus
    uv run tools/mei/incipit_convert.py --g 159 > g159.musicxml  # one work

Verovio reads Plaine & Easie, MusicXML, MEI, **kern, ABC and MuseData, and
writes SVG, MEI, MIDI, Humdrum and Plaine & Easie. It does not write MusicXML.
That single gap is what this module fills, and it is all it tries to do:

    P&E --Verovio--> MEI --parse_mei--> Incipit --to_musicxml--> MusicXML

For anything else, use the tool that already exists. Measured head to head,
each of these matched a hand-written equivalent exactly, so writing your own
buys nothing:

    -> Plaine & Easie   Verovio's renderToPAE(), including from MusicXML input
    -> LilyPond         musicxml2ly, shipped with LilyPond
    -> ABC              xml2abc            <https://wim.vree.org/svgParse/>
    ABC ->              abc2xml, same author; keeps barlines, unlike music21

`Incipit` is the in-memory model everything passes through: clef, key, meter
and a tree of measures holding Note / Rest / Chord / Group (beam, tuplet,
graceGrp). Anything outside the grammar Verovio emits raises Unsupported
rather than degrading quietly.

from_musicxml() is the reverse reader. It earns its place as the verification
counterpart to to_musicxml(): Verovio regenerates beaming on import, so a
Verovio round trip cannot see a broken beam chain -- and one shipped for days
behind a green Verovio check. A reader that trusts our beam markers catches it.

Verified over all 658 Boccherini quartet incipits (`--check`):
  658/658 identical note streams and all 181 trills, read back both by Verovio
  and by from_musicxml. Independently, music21 -- which drops every trill
  reading Verovio's MEI -- reads this MusicXML with 181/181 trills and 337/337
  grace notes intact.

Performance: Verovio's P&E parse is ~98% of the wall clock (~120 incipits/s).
Everything here runs at 10k+/s, so cache the MEI or fan out across processes
rather than optimising this module.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import verovio

MEI = '{http://www.music-encoding.org/ns/mei}'
XML_ID = '{http://www.w3.org/XML/1998/namespace}id'

# MEI @dur -> (MusicXML <type>, LilyPond duration, flags for beaming)
DUR = {'1': ('whole', '1', 0), '2': ('half', '2', 0), '4': ('quarter', '4', 0),
       '8': ('eighth', '8', 1), '16': ('16th', '16', 2), '32': ('32nd', '32', 3),
       '64': ('64th', '64', 4), 'breve': ('breve', '\\breve', 0)}
ALTER = {'f': -1, 's': 1, 'n': 0, 'ff': -2, 'ss': 2, 'x': 2}
ACCNAME = {'f': 'flat', 's': 'sharp', 'n': 'natural', 'ff': 'flat-flat', 'ss': 'double-sharp'}
CLEF = {('G', '2'): ('treble', 'G', 2), ('F', '4'): ('bass', 'F', 4),
        ('C', '3'): ('alto', 'C', 3), ('C', '4'): ('tenor', 'C', 4)}
# fifths -> LilyPond major tonic (incipits carry no mode of their own)
MAJOR = {-7: 'ces', -6: 'ges', -5: 'des', -4: 'aes', -3: 'ees', -2: 'bes', -1: 'f',
         0: 'c', 1: 'g', 2: 'd', 3: 'a', 4: 'e', 5: 'b', 6: 'fis', 7: 'cis'}
DIVISIONS = 96   # divisible by 32 (dotted 64ths) and 3 (tuplets)


# ---------------------------------------------------------------- model

@dataclass
class Note:
    pname: str
    oct: int
    dur: str
    dots: int = 0
    grace: str | None = None          # 'acc' (appoggiatura) | 'unacc' (acciaccatura)
    accid: str | None = None          # written accidental
    alter: int = 0                    # sounding alteration, incl. key signature
    tie_start: bool = False
    tie_end: bool = False
    trill: bool = False
    fermata: bool = False


@dataclass
class Rest:
    dur: str
    dots: int = 0
    measure_rest: bool = False
    num: int = 1
    fermata: bool = False             # P&E `(-)`: a fermata CAN sit on a rest


@dataclass
class Chord:
    dur: str
    dots: int
    notes: list[Note]
    trill: bool = False
    fermata: bool = False


@dataclass
class Group:                           # beam | tuplet | graceGrp
    kind: str
    children: list = field(default_factory=list)
    num: int = 3
    numbase: int = 2


@dataclass
class Measure:
    events: list = field(default_factory=list)
    right: str = 'single'


@dataclass
class Incipit:
    clef: tuple                        # (shape, line)
    fifths: int
    meter: tuple                       # (count, unit, sym)
    measures: list[Measure] = field(default_factory=list)
    label: str = ''
    warnings: list[str] = field(default_factory=list)


class Unsupported(Exception):
    """Something outside the grammar this corpus uses -- fail loudly, never drop."""


# ---------------------------------------------------------------- MEI -> model

def parse_mei(mei: str, label: str = '') -> Incipit:
    root = ET.fromstring(mei)
    music = root.find(MEI + 'music')

    sd = music.iter(MEI + 'staffDef').__next__()
    shape, line = sd.get('clef.shape'), sd.get('clef.line')
    if shape is None:            # round-tripped MEI carries it as a <clef> child
        c = next(music.iter(MEI + 'clef'), None)
        if c is not None:
            shape, line = c.get('shape'), c.get('line')
    if (shape, line) not in CLEF:
        raise Unsupported(f'clef {shape}{line}')

    scoredef = music.iter(MEI + 'scoreDef').__next__()
    meter = (scoredef.get('meter.count'), scoredef.get('meter.unit'), scoredef.get('meter.sym'))

    fifths = 0
    ks = next(music.iter(MEI + 'keySig'), None)
    if ks is not None and ks.get('sig') and ks.get('sig') != '0':
        m = re.fullmatch(r'(\d+)([fs])', ks.get('sig'))
        if not m:
            raise Unsupported(f'key signature {ks.get("sig")}')
        fifths = int(m[1]) * (1 if m[2] == 's' else -1)

    inc = Incipit(clef=(shape, line), fifths=fifths, meter=meter, label=label)
    by_id: dict[str, Note | Chord] = {}

    # Pass 1: every measure's notes, so that ids exist before anything points at them.
    pending = []
    for mel in music.iter(MEI + 'measure'):
        meas = Measure(right=mel.get('right') or 'single')
        layer = next(mel.iter(MEI + 'layer'), None)
        if layer is not None:
            meas.events = [e for e in (_event(c, by_id) for c in layer if _tag(c) != 'clef')
                           if e is not None]
        inc.measures.append(meas)
        pending += [c for c in mel if _tag(c) in ('trill', 'fermata', 'tie')]

    # Pass 2: standoff control events -- the pointers general MEI readers ignore.
    # A tie across a barline starts in one measure and ends in the next, so this
    # cannot be folded into pass 1.
    for ctrl in pending:
        t = _tag(ctrl)
        start = _target(by_id, ctrl.get('startid'))
        if start is None:
            inc.warnings.append(f'<{t}> points at missing id {ctrl.get("startid")}')
            continue
        if t == 'trill':
            start.trill = True
        elif t == 'fermata':
            start.fermata = True
        elif t == 'tie':
            start.tie_start = True
            end = _target(by_id, ctrl.get('endid')) if ctrl.get('endid') else None
            if end is not None:
                end.tie_end = True
            elif ctrl.get('endid'):
                inc.warnings.append(f'<tie> endid {ctrl.get("endid")} missing')
    return inc


def _tag(el):
    return el.tag.split('}')[-1]


def _target(by_id, ref):
    """Resolve a standoff pointer, or None if it dangles.

    Verovio's Plaine & Easie importer occasionally emits a <tie> whose startid
    names no element in the document. Dropping that one tie beats dropping the
    whole incipit, so the caller records it on Incipit.warnings instead."""
    if not ref:
        return None
    return by_id.get(ref.lstrip('#'))


def _event(el, by_id):
    t = _tag(el)
    if t == 'note':
        return _note(el, by_id)
    if t in ('rest', 'mRest', 'multiRest'):
        if t == 'rest':
            r = Rest(dur=el.get('dur'), dots=int(el.get('dots') or 0))
        else:
            r = Rest(dur='1', measure_rest=True, num=int(el.get('num') or 1))
        # Rests must be indexed too: a <fermata> can point at one, and not
        # indexing them makes the fermata look dangling and get dropped.
        if el.get(XML_ID):
            by_id[el.get(XML_ID)] = r
        return r
    if t == 'chord':
        ch = Chord(dur=el.get('dur'), dots=int(el.get('dots') or 0),
                   notes=[_note(n, by_id, inherit=(el.get('dur'), el.get('dots'))) for n in el if _tag(n) == 'note'])
        if el.get(XML_ID):
            by_id[el.get(XML_ID)] = ch
        return ch
    if t in ('beam', 'tuplet', 'graceGrp'):
        g = Group(kind=t, num=int(el.get('num') or 3), numbase=int(el.get('numbase') or 2))
        g.children = [e for e in (_event(c, by_id) for c in el) if e is not None]
        if t == 'graceGrp':
            # Verovio marks the GROUP as ornamental and leaves @grace off its
            # notes, so a reader that only checks note/@grace turns a written-out
            # turn into real notes and breaks the bar's arithmetic.
            _mark_grace(g, el.get('grace') or 'acc')
        return g
    if t in ('barLine', 'space', 'mSpace'):
        # invisible padding; Verovio adds it when re-importing an incipit's
        # incomplete final bar, and it carries no sounding content.
        return None
    raise Unsupported(f'element <{t}>')


def _mark_grace(node, kind):
    for c in node.children:
        if isinstance(c, Group):
            _mark_grace(c, kind)
        elif isinstance(c, Note) and not c.grace:
            c.grace = kind


def _note(el, by_id, inherit=None):
    dur = el.get('dur') or (inherit[0] if inherit else None)
    dots = el.get('dots') or (inherit[1] if inherit else None)
    if dur not in DUR:
        raise Unsupported(f'duration {dur!r}')
    n = Note(pname=el.get('pname'), oct=int(el.get('oct')), dur=dur, dots=int(dots or 0),
             grace=el.get('grace'))
    for a in el:
        if _tag(a) == 'accid':
            if a.get('accid'):
                n.accid = a.get('accid')
            g = a.get('accid.ges') or a.get('accid')
            if g:
                n.alter = ALTER.get(g, 0)
        elif _tag(a) == 'artic':
            raise Unsupported('artic')
    if n.accid and not any(_tag(a) == 'accid' and a.get('accid.ges') for a in el):
        n.alter = ALTER.get(n.accid, 0)
    if el.get(XML_ID):
        by_id[el.get(XML_ID)] = n
    return n


# ---------------------------------------------------------------- helpers

_BEAMID = [0]


def flatten(events, tuplet=None, beam=None, grace_group=False):
    """Walk the event tree, tagging each leaf with its beam/tuplet/grace context."""
    out = []
    for e in events:
        if isinstance(e, Group):
            if e.kind == 'beam':
                _BEAMID[0] += 1
                bid = _BEAMID[0]
                kids = flatten(e.children, tuplet, beam='new', grace_group=grace_group)
                for i, k in enumerate(kids):
                    if k['beam'] == 'new':
                        k['beam'] = ('single' if len(kids) == 1 else
                                     'begin' if i == 0 else 'end' if i == len(kids) - 1 else 'continue')
                        k['beamid'] = bid
                out += kids
            elif e.kind == 'tuplet':
                kids = flatten(e.children, (e.num, e.numbase), beam, grace_group)
                for i, k in enumerate(kids):
                    k['tuplet_pos'] = 'start' if i == 0 else 'stop' if i == len(kids) - 1 else None
                out += kids
            else:                                  # graceGrp
                out += flatten(e.children, tuplet, beam, grace_group=True)
        else:
            out.append({'e': e, 'tuplet': tuplet, 'beam': beam, 'beamid': None,
                        'tuplet_pos': None, 'grace_group': grace_group})
    return out


def dur_fraction(dur, dots, tuplet):
    """Duration in whole notes."""
    base = Fraction(1, int(dur)) if dur != 'breve' else Fraction(2)
    total = base * (2 - Fraction(1, 2 ** dots))
    if tuplet:
        total *= Fraction(tuplet[1], tuplet[0])
    return total


def beam_levels(items):
    """MusicXML wants begin/continue/end per beam level, per note.

    Rests inside a beam carry no beam markers of their own, so they have to be
    transparent here: counting one as a member breaks the chain and the closing
    note gets marked 'begin', leaving the beam open. Group membership comes from
    the beam id assigned in flatten(), not from adjacency.
    """
    flags = [DUR[it['e'].dur][2] if isinstance(it['e'], (Note, Chord)) else 0
             for it in items]
    groups = {}
    for i, it in enumerate(items):
        if it.get('beamid') is not None and flags[i] > 0:
            groups.setdefault(it['beamid'], []).append(i)

    marks = [[] for _ in items]
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        for lv in range(1, max(flags[i] for i in idxs) + 1):
            members = [i for i in idxs if flags[i] >= lv]
            if not members:
                continue
            if len(members) == 1:
                # one note carries this level alone: a hook, pointing back
                # toward the group unless it opens it.
                i = members[0]
                marks[i].append((lv, 'forward hook' if i == idxs[0] else 'backward hook'))
                continue
            for pos, i in enumerate(members):
                marks[i].append((lv, 'begin' if pos == 0 else
                                 'end' if pos == len(members) - 1 else 'continue'))
    return marks


# ---------------------------------------------------------------- MusicXML

def to_musicxml(inc: Incipit) -> str:
    shape, line = inc.clef
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
         '"http://www.musicxml.org/dtds/partwise.dtd">',
         '<score-partwise version="3.1">',
         '  <work><work-title>%s</work-title></work>' % esc(inc.label),
         '  <part-list><score-part id="P1"><part-name>Incipit</part-name></score-part></part-list>',
         '  <part id="P1">']
    for mi, meas in enumerate(inc.measures, 1):
        L.append(f'    <measure number="{mi}">')
        if mi == 1:
            L.append('      <attributes>')
            L.append(f'        <divisions>{DIVISIONS}</divisions>')
            L.append(f'        <key><fifths>{inc.fifths}</fifths></key>')
            cnt, unit, sym = inc.meter
            if sym == 'common':
                L.append('        <time symbol="common"><beats>4</beats><beat-type>4</beat-type></time>')
            elif sym == 'cut':
                L.append('        <time symbol="cut"><beats>2</beats><beat-type>2</beat-type></time>')
            elif cnt:
                L.append(f'        <time><beats>{cnt}</beats><beat-type>{unit}</beat-type></time>')
            L.append(f'        <clef><sign>{shape}</sign><line>{line}</line></clef>')
            L.append('      </attributes>')
        items = flatten(meas.events)
        beams = beam_levels(items)
        for it, bm in zip(items, beams):
            L += _mxl_event(it, bm)
        if meas.right == 'dbl':
            L.append('      <barline location="right"><bar-style>light-light</bar-style></barline>')
        elif meas.right == 'rptend':
            L.append('      <barline location="right"><bar-style>light-heavy</bar-style>'
                     '<repeat direction="backward"/></barline>')
        elif mi == len(inc.measures) and meas.right != 'invis':
            L.append('      <barline location="right"><bar-style>light-heavy</bar-style></barline>')
        L.append('    </measure>')
    L += ['  </part>', '</score-partwise>']
    return '\n'.join(L) + '\n'


def _mxl_event(it, beammarks):
    e, tup = it['e'], it['tuplet']
    out = []
    if isinstance(e, Rest):
        if e.measure_rest:
            out.append('      <note><rest measure="yes"/>'
                       f'<duration>{DIVISIONS * 4}</duration><voice>1</voice></note>')
        else:
            d = int(dur_fraction(e.dur, e.dots, tup) * 4 * DIVISIONS)
            b = [f'      <note><rest/><duration>{d}</duration><voice>1</voice>'
                 f'<type>{DUR[e.dur][0]}</type>{"<dot/>" * e.dots}']
            # A rest inside a tuplet needs the ratio too -- and the tuplet often
            # STARTS on one, so dropping it loses the whole group's timing.
            if tup:
                b.append(f'<time-modification><actual-notes>{tup[0]}</actual-notes>'
                         f'<normal-notes>{tup[1]}</normal-notes></time-modification>')
            nots = []
            if it['tuplet_pos']:
                nots.append(f'<tuplet type="{it["tuplet_pos"]}"/>')
            if e.fermata:
                nots.append('<fermata type="upright"/>')
            if nots:
                b.append('<notations>' + ''.join(nots) + '</notations>')
            b.append('</note>')
            out.append(''.join(b))
        return out

    notes = e.notes if isinstance(e, Chord) else [e]
    for i, n in enumerate(notes):
        grace = getattr(n, 'grace', None)
        d = int(dur_fraction(n.dur, n.dots, tup) * 4 * DIVISIONS)
        b = ['      <note>']
        if grace:
            b.append('<grace%s/>' % (' slash="yes"' if grace == 'unacc' else ''))
        if i:
            b.append('<chord/>')
        b.append(f'<pitch><step>{n.pname.upper()}</step>')
        if n.alter:
            b.append(f'<alter>{n.alter}</alter>')
        b.append(f'<octave>{n.oct}</octave></pitch>')
        if not grace:                       # a grace note must carry no <duration>
            b.append(f'<duration>{d}</duration>')
        if n.tie_end:
            b.append('<tie type="stop"/>')
        if n.tie_start:
            b.append('<tie type="start"/>')
        b.append(f'<voice>1</voice><type>{DUR[n.dur][0]}</type>{"<dot/>" * n.dots}')
        if n.accid:
            b.append(f'<accidental>{ACCNAME.get(n.accid, "natural")}</accidental>')
        if tup:
            b.append(f'<time-modification><actual-notes>{tup[0]}</actual-notes>'
                     f'<normal-notes>{tup[1]}</normal-notes></time-modification>')
        if i == 0:
            for lvl, kind in beammarks:
                b.append(f'<beam number="{lvl}">{kind}</beam>')
        nots = []
        if n.tie_end:
            nots.append('<tied type="stop"/>')
        if n.tie_start:
            nots.append('<tied type="start"/>')
        if it['tuplet_pos'] and i == 0:
            nots.append(f'<tuplet type="{it["tuplet_pos"]}"/>')
        if n.trill or (isinstance(e, Chord) and e.trill and i == 0):
            nots.append('<ornaments><trill-mark/></ornaments>')
        if n.fermata or (isinstance(e, Chord) and e.fermata and i == 0):
            nots.append('<fermata type="upright"/>')
        if nots:
            b.append('<notations>' + ''.join(nots) + '</notations>')
        b.append('</note>')
        out.append(''.join(b))
    return out


def esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ------------------------------------------------------- MusicXML -> Incipit

# The one reader worth having besides Verovio's: almost every notation program
# exports MusicXML, so this turns the module from a P&E fan-out into a hub.
# MusicXML states everything outright, which is exactly what makes it mechanical
# to read -- no sticky state to track, unlike P&E or ABC.

TYPE2DUR = {v[0]: k for k, v in DUR.items()}
ACC2CODE = {v: k for k, v in ACCNAME.items()}


def from_musicxml(xml: str) -> Incipit:
    root = ET.fromstring(xml)
    part = root.find('part')
    if part is None:
        raise Unsupported('no <part> — is this score-partwise MusicXML?')

    clef, fifths, meter = ('G', '2'), 0, (None, None, None)
    at = part.find('measure/attributes')
    if at is not None:
        c = at.find('clef')
        if c is not None:
            clef = (c.findtext('sign'), c.findtext('line'))
        k = at.find('key')
        if k is not None:
            fifths = int(k.findtext('fifths') or 0)
        t = at.find('time')
        if t is not None:
            sym = t.get('symbol')
            meter = ((None, None, 'common') if sym == 'common' else
                     (None, None, 'cut') if sym == 'cut' else
                     (t.findtext('beats'), t.findtext('beat-type'), None))
    if clef not in CLEF:
        raise Unsupported(f'clef {clef}')

    inc = Incipit(clef=clef, fifths=fifths, meter=meter)
    for mel in part.findall('measure'):
        inc.measures.append(Measure(events=_mxl_measure(mel),
                                    right=_mxl_barline(mel)))
    return inc


def _mxl_barline(mel):
    for b in mel.findall('barline'):
        st = b.findtext('bar-style')
        if st == 'light-light':
            return 'dbl'
        if b.find('repeat') is not None:
            return 'rptend'
    return 'single'


def _mxl_measure(mel):
    """Flat MusicXML notes -> our nested beam/tuplet/grace tree.

    MusicXML marks groups with begin/continue/end flags on each note; we need
    them back as nesting. A beam can wrap a tuplet (P&E writes `{(...)}`), so
    the beam opens first and closes last.
    """
    flat = []
    for n in mel.findall('note'):
        ev = _mxl_note(n)
        if ev is None:
            continue
        if n.find('chord') is not None and flat and isinstance(flat[-1][0], (Note, Chord)):
            prev, meta = flat[-1]
            if isinstance(prev, Note):
                ch = Chord(dur=prev.dur, dots=prev.dots, notes=[prev],
                           trill=prev.trill, fermata=prev.fermata)
                flat[-1] = (ch, meta)
                prev = ch
            prev.notes.append(ev[0])
            continue
        flat.append(ev)

    out, stack = [], []                      # stack of (kind, Group)
    def sink():
        return stack[-1][1].children if stack else out

    for ev, m in flat:
        if m['beam'] == 'begin':
            g = Group(kind='beam')
            sink().append(g)
            stack.append(('beam', g))
        if m['tuplet'] == 'start':
            g = Group(kind='tuplet', num=m['num'], numbase=m['numbase'])
            sink().append(g)
            stack.append(('tuplet', g))
        sink().append(ev)
        # Close innermost-first. A beam can sit inside a tuplet, in which case
        # both end on this note; popping only the outer one leaves the tuplet
        # open and every later note inherits its ratio.
        cb, ct = m['beam'] == 'end', m['tuplet'] == 'stop'
        while stack and ((stack[-1][0] == 'beam' and cb) or
                         (stack[-1][0] == 'tuplet' and ct)):
            kind, _ = stack.pop()
            if kind == 'beam':
                cb = False
            else:
                ct = False
    return _regroup_graces(out)


def _all_grace(ev):
    if isinstance(ev, Note):
        return bool(ev.grace)
    if isinstance(ev, Group):
        return bool(ev.children) and all(_all_grace(c) for c in ev.children)
    return False


def _count_grace(ev):
    if isinstance(ev, Note):
        return 1
    if isinstance(ev, Group):
        return sum(_count_grace(c) for c in ev.children)
    return 0


def _regroup_graces(events):
    """MusicXML has no grace-GROUP: it just emits consecutive grace notes.

    P&E does distinguish them (`qq...r`), so a run of two or more adjacent
    ornamental notes is put back into a graceGrp -- otherwise the reconstructed
    P&E spells one turn figure as several separate appoggiaturas.
    """
    out, i = [], 0
    while i < len(events):
        if _all_grace(events[i]):
            j = i
            while j < len(events) and _all_grace(events[j]):
                j += 1
            if sum(_count_grace(e) for e in events[i:j]) > 1:
                out.append(Group(kind='graceGrp', children=events[i:j]))
            else:
                out += events[i:j]
            i = j
        else:
            out.append(events[i])
            i += 1
    return out


def _mxl_note(n):
    grace = n.find('grace')
    typ = n.findtext('type')
    if typ is None:
        if n.find('rest') is not None:                 # whole-measure rest
            return Rest(dur='1', measure_rest=True), _mxl_meta(n)
        raise Unsupported('note with no <type>')
    if typ not in TYPE2DUR:
        raise Unsupported(f'duration type {typ!r}')
    dur, dots = TYPE2DUR[typ], len(n.findall('dot'))

    if n.find('rest') is not None:
        r = Rest(dur=dur, dots=dots)
        r.measure_rest = n.find('rest').get('measure') == 'yes'
        nots = n.find('notations')
        if nots is not None and nots.find('fermata') is not None:
            r.fermata = True
        return r, _mxl_meta(n)

    p = n.find('pitch')
    if p is None:
        return None
    note = Note(pname=p.findtext('step').lower(), oct=int(p.findtext('octave')),
                dur=dur, dots=dots,
                grace=(None if grace is None else
                       ('unacc' if grace.get('slash') == 'yes' else 'acc')),
                alter=int(float(p.findtext('alter') or 0)))
    a = n.findtext('accidental')
    if a:
        note.accid = ACC2CODE.get(a, 'n')
    nots = n.find('notations')
    if nots is not None:
        for t in nots.findall('tied'):
            if t.get('type') == 'start':
                note.tie_start = True
            elif t.get('type') == 'stop':
                note.tie_end = True
        if nots.find('ornaments/trill-mark') is not None:
            note.trill = True
        if nots.find('fermata') is not None:
            note.fermata = True
    return note, _mxl_meta(n)


def _mxl_meta(n):
    beam = None
    for b in n.findall('beam'):
        if b.get('number') in (None, '1'):
            beam = (b.text or '').strip()
    tm = n.find('time-modification')
    num = int(tm.findtext('actual-notes')) if tm is not None else 3
    base = int(tm.findtext('normal-notes')) if tm is not None else 2
    tup = None
    nots = n.find('notations')
    if nots is not None:
        t = nots.find('tuplet')
        if t is not None:
            tup = t.get('type')
    return {'beam': beam, 'tuplet': tup, 'num': num, 'numbase': base}


# ---------------------------------------------------------------- driver

def engraver():
    """A Verovio toolkit configured to read Plaine & Easie."""
    tk = verovio.toolkit()
    tk.setOptions({'inputFrom': 'pae', 'xmlIdSeed': 1})
    return tk


def pae_to_mei(tk, pae):
    if not tk.loadData(pae):
        raise Unsupported('Verovio could not parse this Plaine & Easie')
    return tk.getMEI()


def convert(pae, label='', tk=None):
    """Plaine & Easie -> MusicXML, the one hop Verovio will not do."""
    tk = tk or engraver()
    return to_musicxml(parse_mei(pae_to_mei(tk, pae), label))


# ---------------------------------------------------------------- self-check

SHARPS = 'fcgdaeb'
FLATS = 'beadgcf'


def keysig_state(fifths):
    st = {p: 0 for p in 'abcdefg'}
    for p in (SHARPS[:fifths] if fifths > 0 else FLATS[:-fifths]):
        st[p] = 1 if fifths > 0 else -1
    return st


def note_stream(inc: Incipit):
    """(pitch, SOUNDING alter, octave, duration-in-whole-notes, grace?) per note.

    The alteration is recomputed from the key signature plus written accidentals
    rather than read off @accid.ges: Verovio spells key-signature alterations
    explicitly on import but leaves them implicit on re-import, so only the
    effective pitch is comparable across a round trip."""
    out = []
    for meas in inc.measures:
        st = keysig_state(inc.fifths)
        for it in flatten(meas.events):
            e = it['e']
            ns = e.notes if isinstance(e, Chord) else ([e] if isinstance(e, Note) else [])
            for n in ns:
                if n.accid:
                    st[n.pname] = ALTER.get(n.accid, 0)
                out.append((n.pname, st[n.pname], n.oct,
                            None if n.grace else dur_fraction(n.dur, n.dots, it['tuplet']),
                            bool(n.grace)))
    return out


def ornaments(inc: Incipit):
    t = f_ = ties = 0
    for meas in inc.measures:
        for it in flatten(meas.events):
            e = it['e']
            if isinstance(e, Rest):
                f_ += e.fermata
                continue
            for n in (e.notes if isinstance(e, Chord) else [e]):
                if isinstance(n, Note):
                    t += n.trill
                    f_ += n.fermata
                    ties += n.tie_start
    return t, f_, ties


def check(rows):
    """Round-trip the corpus two ways and report.

    Verovio catches semantics; from_musicxml catches notation. Both are needed:
    Verovio re-beams on import, so it cannot see a broken beam chain, and that
    bug shipped for days behind a green Verovio round trip.
    """
    import time
    tk = engraver()
    back = verovio.toolkit()
    back.setOptions({'inputFrom': 'musicxml', 'xmlIdSeed': 1})

    t0 = time.perf_counter()
    incs = [parse_mei(pae_to_mei(tk, r['pae']), f"G {r['gerard']}") for r in rows]
    t_parse = time.perf_counter() - t0

    results = {}
    for name, reader in (('Verovio', lambda x: parse_mei(back.getMEI())
                          if back.loadData(x) else None),
                         ('from_musicxml', from_musicxml)):
        ok = bad = rej = 0
        orn_in = orn_out = 0
        fails = []
        for src in incs:
            try:
                rt = reader(to_musicxml(src))
            except Unsupported as e:
                rej += 1
                fails.append((src.label, str(e)))
                continue
            if rt is None:
                rej += 1
                fails.append((src.label, 'reader rejected our MusicXML'))
                continue
            a, b = note_stream(src), note_stream(rt)
            oa, ob = ornaments(src), ornaments(rt)
            orn_in += oa[0]
            orn_out += ob[0]
            if a == b and oa == ob:
                ok += 1
            else:
                bad += 1
                if len(fails) < 3:
                    d = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y),
                             min(len(a), len(b)))
                    fails.append((src.label, f'notes {len(a)}->{len(b)} orn {oa}->{ob} @{d}'))
        results[name] = (ok, bad, rej, orn_in, orn_out, fails)

    print(f'{len(rows)} incipits, P&E -> MusicXML -> back\n')
    print(f'{"read back by":16s} {"exact":>7s} {"differs":>8s} {"rejected":>9s} {"trills":>10s}   catches')
    for name, (ok, bad, rej, oi, oo, fails) in results.items():
        what = ('semantics; blind to beaming, which it regenerates'
                if name == 'Verovio' else 'notation: beams, tuplet nesting, grace groups')
        print(f'{name:16s} {ok:7d} {bad:8d} {rej:9d} {f"{oo}/{oi}":>10s}   {what}')
        for g, m in fails[:3]:
            print(f'    ! {g}: {m}')

    warned = sum(1 for i in incs if i.warnings)
    if warned:
        print(f'\n  {warned} incipits carried unresolved MEI references (see Incipit.warnings)')
    print(f'\nthroughput: P&E -> Incipit {len(rows) / t_parse:,.0f}/s '
          f'(Verovio\'s parse is ~98% of it)')
    return 0 if all(b == r == 0 for _, b, r, *_ in results.values()) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', type=Path, default=Path('boccherini-rism-incipits.jsonl'),
                    help='JSONL corpus with a "pae" field per row')
    ap.add_argument('--g', help='only this Gérard number')
    ap.add_argument('--check', action='store_true', help='round-trip the corpus and report')
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()

    rows = [json.loads(l) for l in a.src.read_text().splitlines() if l.strip()]
    if a.g:
        rows = [r for r in rows if r['gerard'] == a.g]
    if a.check:
        return check(rows[:a.limit] if a.limit else rows)

    tk = engraver()
    for r in (rows[:a.limit] if a.limit else rows):
        label = f"G {r['gerard']} — {r['caption'] or ''} ({r['part'] or ''})"
        sys.stdout.write(to_musicxml(parse_mei(pae_to_mei(tk, r['pae']), label)))
        sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
