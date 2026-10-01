"""What stands behind an item's Gérard label. One definition, imported by everything.

Three scripts need this — the shelf, the concordance and the audit — and three copies of a
rule like this is how they drift apart. `STATE-OF-EVIDENCE.md` is generated from the same
function, so the counts in the documents and the badges on the page cannot disagree.

    A  a person looked at the pages and wrote down what they saw
    B  a person established it from the scan; recorded in corrections.json
    C  RISM's own record *for this copy* carries the GerB number
    D  asserted from a title page, a filename or a portal description; never checked
    E  the pages disagree with the label
    F  nothing supports it

C is corroboration by a catalogue, not verification. RISM has been wrong here — all seven
F-Po autographs carry one shelfmark and only one of them is right.
"""
import json
from pathlib import Path

STORE = Path('structure')
LABEL = {
    'A': 'checked by eye',
    'B': 'established from the scan',
    'C': 'RISM states it for this copy',
    'D': 'asserted, never checked',
    'E': 'pages disagree with the label',
    'F': 'nothing supports it',
}


def reading(scan_id):
    f = STORE / f'{scan_id}.json'
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except Exception:
        return None


def tier_of(m, st=None):
    """(tier, label). `m` is the item's metadata.json, `st` its structure reading."""
    if m.get('contents_verified'):
        return 'A', LABEL['A']
    if m.get('corrected'):
        return 'B', LABEL['B']
    if st and st.get('read') and st.get('disagreements'):
        return 'E', LABEL['E']
    has_g = bool(m.get('gerard') or m.get('gerard_numbers'))
    if m.get('rism_relation') == 'copy' and has_g and not (
            m.get('gerard_established_by') or m.get('established_by')):
        return 'C', LABEL['C']
    if m.get('gerard_established_by') or m.get('established_by'):
        return 'D', LABEL['D']
    return ('C', LABEL['C']) if (m.get('rism_relation') == 'copy' and has_g) else \
           ('F', LABEL['F'])
