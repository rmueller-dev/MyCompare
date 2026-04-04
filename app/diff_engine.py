"""
Dual-engine diff with mandatory verification layer.

Engine A: Structural diff (format-aware)
Engine B: Plain-text diff (difflib.SequenceMatcher with autojunk=False)

Verification: SHA-256 hash check + character count cross-check.
"""
import difflib
import hashlib
from typing import List, Dict, Any, Tuple


def compute_hash(text: str) -> str:
    """SHA-256 of text content."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Engine B: Plain-text line diff (used for ALL file types)
# ---------------------------------------------------------------------------

def plaintext_diff(text_a: str, text_b: str) -> List[Dict[str, Any]]:
    """
    Line-by-line diff using SequenceMatcher with autojunk=False.
    Returns list of change dicts.
    """
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    sm = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        change = {
            'type': tag,  # 'replace', 'insert', 'delete'
            'old_start': i1,
            'old_end': i2,
            'new_start': j1,
            'new_end': j2,
            'old_lines': lines_a[i1:i2],
            'new_lines': lines_b[j1:j2],
            'engine': 'plaintext',
        }
        changes.append(change)

    return changes


def word_level_diff(old_text: str, new_text: str) -> List[Dict[str, Any]]:
    """
    Word-level diff for more granular change detection.
    Splits on whitespace boundaries while preserving whitespace.
    """
    import re
    # Split into tokens (words and whitespace)
    tokens_a = re.findall(r'\S+|\s+', old_text)
    tokens_b = re.findall(r'\S+|\s+', new_text)

    sm = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        changes.append({
            'type': tag,
            'old_tokens': tokens_a[i1:i2],
            'new_tokens': tokens_b[j1:j2],
            'engine': 'word',
        })

    return changes


# ---------------------------------------------------------------------------
# Engine A: Structural diffs per file type
# ---------------------------------------------------------------------------

def structural_diff_docx(struct_a: list, struct_b: list) -> List[Dict[str, Any]]:
    """Paragraph-level structural diff for DOCX."""
    texts_a = [p['text'] for p in struct_a]
    texts_b = [p['text'] for p in struct_b]

    sm = difflib.SequenceMatcher(None, texts_a, texts_b, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        change = {
            'type': tag,
            'location': f'Absatz {i1 + 1}' if tag != 'insert' else f'Nach Absatz {i1}',
            'old_items': struct_a[i1:i2],
            'new_items': struct_b[j1:j2],
            'engine': 'structural',
        }
        # For replacements, compute word-level diffs for each pair
        if tag == 'replace':
            inline_diffs = []
            for idx in range(max(len(change['old_items']), len(change['new_items']))):
                old_t = change['old_items'][idx]['text'] if idx < len(change['old_items']) else ''
                new_t = change['new_items'][idx]['text'] if idx < len(change['new_items']) else ''
                if old_t != new_t:
                    inline_diffs.append({
                        'old_text': old_t,
                        'new_text': new_t,
                        'word_changes': word_level_diff(old_t, new_t),
                    })
            change['inline_diffs'] = inline_diffs
        changes.append(change)

    return changes


def structural_diff_xlsx(struct_a: list, struct_b: list) -> List[Dict[str, Any]]:
    """Cell-level structural diff for XLSX."""
    # Build coord->text maps
    map_a = {c['coord']: c['text'] for c in struct_a}
    map_b = {c['coord']: c['text'] for c in struct_b}
    all_coords = sorted(set(list(map_a.keys()) + list(map_b.keys())))

    changes = []
    for coord in all_coords:
        val_a = map_a.get(coord)
        val_b = map_b.get(coord)
        if val_a == val_b:
            continue
        if val_a is None:
            changes.append({
                'type': 'insert',
                'location': coord,
                'old_text': '',
                'new_text': val_b,
                'engine': 'structural',
            })
        elif val_b is None:
            changes.append({
                'type': 'delete',
                'location': coord,
                'old_text': val_a,
                'new_text': '',
                'engine': 'structural',
            })
        else:
            changes.append({
                'type': 'replace',
                'location': coord,
                'old_text': val_a,
                'new_text': val_b,
                'word_changes': word_level_diff(val_a, val_b),
                'engine': 'structural',
            })

    return changes


def structural_diff_pptx(struct_a: list, struct_b: list) -> List[Dict[str, Any]]:
    """Shape-level structural diff for PPTX."""
    # Build key->text maps
    def make_key(item):
        return f"Slide{item['slide']}.{item['shape']}"

    map_a = {}
    for item in struct_a:
        k = make_key(item)
        map_a.setdefault(k, []).append(item['text'])
    map_b = {}
    for item in struct_b:
        k = make_key(item)
        map_b.setdefault(k, []).append(item['text'])

    all_keys = sorted(set(list(map_a.keys()) + list(map_b.keys())))
    changes = []

    for key in all_keys:
        texts_a = map_a.get(key, [])
        texts_b = map_b.get(key, [])
        if texts_a == texts_b:
            continue

        old_text = '\n'.join(texts_a)
        new_text = '\n'.join(texts_b)

        if not texts_a:
            ctype = 'insert'
        elif not texts_b:
            ctype = 'delete'
        else:
            ctype = 'replace'

        changes.append({
            'type': ctype,
            'location': key,
            'old_text': old_text,
            'new_text': new_text,
            'word_changes': word_level_diff(old_text, new_text) if ctype == 'replace' else [],
            'engine': 'structural',
        })

    return changes


def structural_diff_pdf(struct_a: list, struct_b: list) -> List[Dict[str, Any]]:
    """Page-level structural diff for PDF."""
    texts_a = [p['text'] for p in struct_a]
    texts_b = [p['text'] for p in struct_b]

    sm = difflib.SequenceMatcher(None, texts_a, texts_b, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        change = {
            'type': tag,
            'location': f'Seite {i1 + 1}' if tag != 'insert' else f'Nach Seite {i1}',
            'old_items': struct_a[i1:i2],
            'new_items': struct_b[j1:j2],
            'engine': 'structural',
        }
        if tag == 'replace':
            inline_diffs = []
            for idx in range(max(i2 - i1, j2 - j1)):
                old_t = texts_a[i1 + idx] if (i1 + idx) < i2 else ''
                new_t = texts_b[j1 + idx] if (j1 + idx) < j2 else ''
                if old_t != new_t:
                    inline_diffs.append({
                        'old_text': old_t,
                        'new_text': new_t,
                        'word_changes': word_level_diff(old_t, new_t),
                    })
            change['inline_diffs'] = inline_diffs
        changes.append(change)

    return changes


STRUCTURAL_DIFFERS = {
    'docx': structural_diff_docx,
    'xlsx': structural_diff_xlsx,
    'pptx': structural_diff_pptx,
    'pdf': structural_diff_pdf,
}


# ---------------------------------------------------------------------------
# Verification Layer
# ---------------------------------------------------------------------------

def verify_diff(text_a: str, text_b: str, all_changes: list) -> Dict[str, Any]:
    """
    Mandatory verification pass.
    Step 2: Hash check
    Step 3: Character count cross-check
    Step 4: Verification badge
    """
    hash_a = compute_hash(text_a)
    hash_b = compute_hash(text_b)
    hashes_equal = hash_a == hash_b
    has_changes = len(all_changes) > 0

    # Character counts from detected changes
    total_added_chars = 0
    total_deleted_chars = 0

    for change in all_changes:
        if 'old_lines' in change:
            total_deleted_chars += sum(len(l) for l in change['old_lines'])
            total_added_chars += sum(len(l) for l in change['new_lines'])
        elif 'old_text' in change:
            total_deleted_chars += len(change.get('old_text', ''))
            total_added_chars += len(change.get('new_text', ''))
        elif 'old_items' in change:
            for item in change.get('old_items', []):
                total_deleted_chars += len(item.get('text', ''))
            for item in change.get('new_items', []):
                total_added_chars += len(item.get('text', ''))

    expected_delta = len(text_b) - len(text_a)
    actual_delta = total_added_chars - total_deleted_chars
    delta_mismatch = abs(expected_delta - actual_delta)

    # Determine verification status
    if hashes_equal and not has_changes:
        status = 'green'
        message = 'Vollständig verifiziert'
        detail = 'Keine Änderungen erkannt. SHA-256 Hashes stimmen überein.'
    elif not hashes_equal and not has_changes:
        # CRITICAL: hashes differ but no changes found
        status = 'red'
        message = 'Verifikationsfehler — manuelle Prüfung erforderlich'
        detail = 'Änderungen erkannt (SHA-256 Hashes unterschiedlich) aber nicht dargestellt. Datei manuell prüfen!'
    elif hashes_equal and has_changes:
        # Shouldn't happen — changes found but hashes equal
        status = 'red'
        message = 'Verifikationsfehler — manuelle Prüfung erforderlich'
        detail = 'Änderungen dargestellt aber SHA-256 Hashes identisch. Möglicher Fehler in der Extraktion.'
    elif delta_mismatch == 0:
        status = 'green'
        message = 'Vollständig verifiziert'
        detail = f'{len(all_changes)} Änderung(en) erkannt. SHA-256 und Zeichenanzahl verifiziert.'
    elif delta_mismatch <= 50:
        status = 'yellow'
        message = f'Teilweise verifiziert — {delta_mismatch} Zeichen nicht zugeordnet'
        detail = (f'{len(all_changes)} Änderung(en) erkannt. '
                  f'Zeichenanzahl stimmt nicht vollständig überein (Δ {delta_mismatch} Zeichen nicht zugeordnet). '
                  f'Dies kann durch Formatierungsunterschiede bei der Extraktion entstehen.')
    else:
        status = 'yellow'
        message = f'Teilweise verifiziert — {delta_mismatch} Zeichen nicht zugeordnet'
        detail = (f'{len(all_changes)} Änderung(en) erkannt. '
                  f'Verifikationswarnung: Zeichenanzahl stimmt nicht überein '
                  f'(Δ {delta_mismatch} Zeichen nicht zugeordnet). Manuelle Prüfung empfohlen.')

    return {
        'status': status,
        'message': message,
        'detail': detail,
        'hash_a': hash_a,
        'hash_b': hash_b,
        'hashes_equal': hashes_equal,
        'total_added_chars': total_added_chars,
        'total_deleted_chars': total_deleted_chars,
        'expected_delta': expected_delta,
        'actual_delta': actual_delta,
        'delta_mismatch': delta_mismatch,
        'change_count': len(all_changes),
    }


# ---------------------------------------------------------------------------
# Main diff function
# ---------------------------------------------------------------------------

def compute_diff(struct_a, text_a, struct_b, text_b, file_type):
    """
    Dual-engine diff with verification.
    Returns the union of structural + plaintext changes, plus verification report.
    """
    # Engine A: structural diff
    structural_differ = STRUCTURAL_DIFFERS.get(file_type)
    structural_changes = structural_differ(struct_a, struct_b) if structural_differ else []

    # Engine B: plain-text diff
    pt_changes = plaintext_diff(text_a, text_b)

    # Union: include all changes from both engines
    # Structural changes are the primary display; plaintext changes catch anything missed
    all_changes_for_verification = structural_changes + pt_changes

    # Verification
    verification = verify_diff(text_a, text_b, all_changes_for_verification)

    # Build unified diff display from plaintext for side-by-side view
    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()
    sm = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)

    unified_lines = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for idx in range(i1, i2):
                unified_lines.append({
                    'type': 'equal',
                    'left_num': idx + 1,
                    'right_num': j1 + (idx - i1) + 1,
                    'left_text': lines_a[idx],
                    'right_text': lines_b[j1 + (idx - i1)],
                })
        elif tag == 'replace':
            max_len = max(i2 - i1, j2 - j1)
            for idx in range(max_len):
                left_idx = i1 + idx if (i1 + idx) < i2 else None
                right_idx = j1 + idx if (j1 + idx) < j2 else None
                left_t = lines_a[left_idx] if left_idx is not None else ''
                right_t = lines_b[right_idx] if right_idx is not None else ''
                # Compute inline word diff for this line pair
                inline = word_level_diff(left_t, right_t) if left_t or right_t else []
                unified_lines.append({
                    'type': 'replace',
                    'left_num': (left_idx + 1) if left_idx is not None else None,
                    'right_num': (right_idx + 1) if right_idx is not None else None,
                    'left_text': left_t,
                    'right_text': right_t,
                    'inline_diff': inline,
                })
        elif tag == 'delete':
            for idx in range(i1, i2):
                unified_lines.append({
                    'type': 'delete',
                    'left_num': idx + 1,
                    'right_num': None,
                    'left_text': lines_a[idx],
                    'right_text': '',
                })
        elif tag == 'insert':
            for idx in range(j1, j2):
                unified_lines.append({
                    'type': 'insert',
                    'left_num': None,
                    'right_num': idx + 1,
                    'left_text': '',
                    'right_text': lines_b[idx],
                })

    return {
        'structural_changes': structural_changes,
        'plaintext_changes': pt_changes,
        'unified_lines': unified_lines,
        'verification': verification,
        'summary': {
            'structural_count': len(structural_changes),
            'plaintext_count': len(pt_changes),
            'total_lines_a': len(lines_a),
            'total_lines_b': len(lines_b),
        },
    }
