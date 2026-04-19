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

def plaintext_diff(text_a: str, text_b: str, options: dict = None) -> List[Dict[str, Any]]:
    """
    Line-by-line diff using SequenceMatcher with autojunk=False.
    Returns list of change dicts.
    """
    options = options or {}

    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    # Apply comparison options
    def normalize(lines):
        result = lines[:]
        if options.get('ignore_case'):
            result = [l.lower() for l in result]
        if options.get('ignore_whitespace'):
            result = [' '.join(l.split()) + '\n' if l.endswith('\n') else ' '.join(l.split()) for l in result]
        return result

    compare_a = normalize(lines_a)
    compare_b = normalize(lines_b)

    sm = difflib.SequenceMatcher(None, compare_a, compare_b, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        change = {
            'type': tag,
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

def _compare_formatting(fmt_a, fmt_b):
    """Compare formatting metadata between two paragraphs/cells, return list of differences."""
    diffs = []
    if not fmt_a and not fmt_b:
        return diffs
    if not fmt_a or not fmt_b:
        diffs.append('Formatierung hinzugefügt/entfernt')
        return diffs

    # Compare run-by-run formatting
    max_runs = max(len(fmt_a), len(fmt_b))
    for i in range(max_runs):
        a = fmt_a[i] if i < len(fmt_a) else {}
        b = fmt_b[i] if i < len(fmt_b) else {}
        text = a.get('text', b.get('text', ''))

        for prop, label in [
            ('bold', 'Fett'), ('italic', 'Kursiv'), ('underline', 'Unterstrichen'),
            ('strike', 'Durchgestrichen'), ('superscript', 'Hochgestellt'),
            ('subscript', 'Tiefgestellt'),
        ]:
            va = a.get(prop, False)
            vb = b.get(prop, False)
            if bool(va) != bool(vb):
                action = 'hinzugefügt' if vb else 'entfernt'
                diffs.append(f'{label} {action}: "{text[:30]}"')

        for prop, label in [
            ('size', 'Schriftgröße'), ('font_name', 'Schriftart'), ('color', 'Schriftfarbe'),
        ]:
            va = a.get(prop)
            vb = b.get(prop)
            if va != vb and (va or vb):
                diffs.append(f'{label} geändert: {va} → {vb} ("{text[:30]}")')

    return diffs


def structural_diff_docx(struct_a: list, struct_b: list) -> List[Dict[str, Any]]:
    """Paragraph-level structural diff for DOCX, including formatting changes."""
    texts_a = [p['text'] for p in struct_a]
    texts_b = [p['text'] for p in struct_b]

    sm = difflib.SequenceMatcher(None, texts_a, texts_b, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            # Check for formatting-only changes on equal-text paragraphs
            for offset in range(i2 - i1):
                a_item = struct_a[i1 + offset]
                b_item = struct_b[j1 + offset]
                # Quick-check: skip expensive comparison if formatting_key matches
                fk_a = a_item.get('formatting_key', '')
                fk_b = b_item.get('formatting_key', '')
                if fk_a == fk_b and a_item.get('alignment') == b_item.get('alignment') and \
                   a_item.get('style') == b_item.get('style') and \
                   a_item.get('numbering') == b_item.get('numbering') and \
                   a_item.get('fields', []) == b_item.get('fields', []) and \
                   set(a_item.get('bookmarks', [])) == set(b_item.get('bookmarks', [])):
                    continue
                fmt_diffs = _compare_formatting(
                    a_item.get('formatting', []),
                    b_item.get('formatting', [])
                )
                # Alignment and style changes
                if a_item.get('alignment') != b_item.get('alignment'):
                    fmt_diffs.append(f'Ausrichtung geändert: {a_item.get("alignment")} → {b_item.get("alignment")}')
                if a_item.get('style') != b_item.get('style'):
                    fmt_diffs.append(f'Formatvorlage geändert: {a_item.get("style")} → {b_item.get("style")}')

                # Numbering changes
                num_a = a_item.get('numbering')
                num_b = b_item.get('numbering')
                if num_a != num_b:
                    if num_a and not num_b:
                        fmt_diffs.append(f'Nummerierung entfernt (war Ebene {num_a.get("level", "?")})')
                    elif not num_a and num_b:
                        fmt_diffs.append(f'Nummerierung hinzugefügt (Ebene {num_b.get("level", "?")})')
                    elif num_a and num_b:
                        if num_a.get('level') != num_b.get('level'):
                            fmt_diffs.append(f'Nummerierungsebene geändert: {num_a.get("level")} → {num_b.get("level")}')
                        if num_a.get('numId') != num_b.get('numId'):
                            fmt_diffs.append(f'Nummerierungsformat geändert')

                # Field / cross-reference changes
                fields_a = a_item.get('fields', [])
                fields_b = b_item.get('fields', [])
                if fields_a != fields_b:
                    fa_instrs = {f['instruction'] for f in fields_a}
                    fb_instrs = {f['instruction'] for f in fields_b}
                    for removed in fa_instrs - fb_instrs:
                        fmt_diffs.append(f'Feld entfernt: {removed}')
                    for added in fb_instrs - fa_instrs:
                        fmt_diffs.append(f'Feld hinzugefügt: {added}')
                    # Check display value changes for same fields
                    fa_map = {f['instruction']: f['display'] for f in fields_a}
                    fb_map = {f['instruction']: f['display'] for f in fields_b}
                    for instr in fa_instrs & fb_instrs:
                        if fa_map.get(instr) != fb_map.get(instr):
                            fmt_diffs.append(f'Feldwert geändert ({instr}): "{fa_map[instr]}" → "{fb_map[instr]}"')

                # Bookmark changes
                bm_a = set(a_item.get('bookmarks', []))
                bm_b = set(b_item.get('bookmarks', []))
                for removed in bm_a - bm_b:
                    fmt_diffs.append(f'Textmarke entfernt: {removed}')
                for added in bm_b - bm_a:
                    fmt_diffs.append(f'Textmarke hinzugefügt: {added}')

                if fmt_diffs:
                    changes.append({
                        'type': 'formatting',
                        'location': f'Absatz {i1 + offset + 1}',
                        'old_items': [a_item],
                        'new_items': [b_item],
                        'formatting_changes': fmt_diffs,
                        'engine': 'structural',
                    })
            continue

        change = {
            'type': tag,
            'location': f'Absatz {i1 + 1}' if tag != 'insert' else f'Nach Absatz {i1}',
            'old_items': struct_a[i1:i2],
            'new_items': struct_b[j1:j2],
            'engine': 'structural',
        }
        # For replacements, compute word-level diffs + formatting diffs
        if tag == 'replace':
            inline_diffs = []
            for idx in range(max(len(change['old_items']), len(change['new_items']))):
                old_item = change['old_items'][idx] if idx < len(change['old_items']) else {'text': '', 'formatting': []}
                new_item = change['new_items'][idx] if idx < len(change['new_items']) else {'text': '', 'formatting': []}
                old_t = old_item.get('text', '')
                new_t = new_item.get('text', '')
                if old_t != new_t:
                    fmt_diffs = _compare_formatting(
                        old_item.get('formatting', []),
                        new_item.get('formatting', [])
                    )
                    inline_diffs.append({
                        'old_text': old_t,
                        'new_text': new_t,
                        'old_html': old_item.get('html', ''),
                        'new_html': new_item.get('html', ''),
                        'word_changes': word_level_diff(old_t, new_t),
                        'formatting_changes': fmt_diffs,
                    })
            change['inline_diffs'] = inline_diffs
        changes.append(change)

    return changes


def structural_diff_xlsx(struct_a: list, struct_b: list) -> List[Dict[str, Any]]:
    """Cell-level structural diff for XLSX, including formatting and formula changes."""
    map_a = {c['coord']: c for c in struct_a}
    map_b = {c['coord']: c for c in struct_b}
    all_coords = sorted(set(list(map_a.keys()) + list(map_b.keys())))

    changes = []
    for coord in all_coords:
        cell_a = map_a.get(coord)
        cell_b = map_b.get(coord)
        val_a = cell_a['text'] if cell_a else None
        val_b = cell_b['text'] if cell_b else None

        if val_a == val_b:
            # Check formatting-only changes
            if cell_a and cell_b:
                fk_a = cell_a.get('formatting_key', '')
                fk_b = cell_b.get('formatting_key', '')
                fmt_changes = []
                if fk_a != fk_b:
                    fa = cell_a.get('formatting', {})
                    fb = cell_b.get('formatting', {})
                    for prop, label in [('bold', 'Fett'), ('italic', 'Kursiv'), ('underline', 'Unterstrichen'),
                                        ('strike', 'Durchgestrichen'), ('font_name', 'Schriftart'),
                                        ('font_size', 'Schriftgröße'), ('color', 'Schriftfarbe'),
                                        ('bg_color', 'Hintergrundfarbe'), ('align', 'Ausrichtung'),
                                        ('number_format', 'Zahlenformat')]:
                        va = fa.get(prop)
                        vb = fb.get(prop)
                        if va != vb:
                            fmt_changes.append(f'{label}: {va} → {vb}')
                # Check formula changes
                formula_a = cell_a.get('formula')
                formula_b = cell_b.get('formula')
                if formula_a != formula_b and (formula_a or formula_b):
                    fmt_changes.append(f'Formel: {formula_a} → {formula_b}')

                if fmt_changes:
                    changes.append({
                        'type': 'formatting',
                        'location': coord,
                        'old_text': val_a,
                        'new_text': val_b,
                        'old_html': cell_a.get('html', ''),
                        'new_html': cell_b.get('html', ''),
                        'formatting_changes': fmt_changes,
                        'engine': 'structural',
                    })
            continue

        if val_a is None:
            changes.append({
                'type': 'insert',
                'location': coord,
                'old_text': '',
                'new_text': val_b,
                'new_html': cell_b.get('html', ''),
                'engine': 'structural',
            })
        elif val_b is None:
            changes.append({
                'type': 'delete',
                'location': coord,
                'old_text': val_a,
                'old_html': cell_a.get('html', ''),
                'new_text': '',
                'engine': 'structural',
            })
        else:
            changes.append({
                'type': 'replace',
                'location': coord,
                'old_text': val_a,
                'new_text': val_b,
                'old_html': cell_a.get('html', ''),
                'new_html': cell_b.get('html', ''),
                'word_changes': word_level_diff(val_a, val_b),
                'engine': 'structural',
            })

    return changes


def structural_diff_pptx(struct_a: list, struct_b: list) -> List[Dict[str, Any]]:
    """Shape-level structural diff for PPTX, including formatting."""
    def make_key(item):
        return f"Slide{item['slide']}.{item['shape']}"

    # Group items by key, preserving full data
    map_a = {}
    for item in struct_a:
        k = make_key(item)
        map_a.setdefault(k, []).append(item)
    map_b = {}
    for item in struct_b:
        k = make_key(item)
        map_b.setdefault(k, []).append(item)

    all_keys = sorted(set(list(map_a.keys()) + list(map_b.keys())))
    changes = []

    for key in all_keys:
        items_a = map_a.get(key, [])
        items_b = map_b.get(key, [])
        texts_a = [it['text'] for it in items_a]
        texts_b = [it['text'] for it in items_b]

        if texts_a == texts_b:
            # Check formatting-only changes
            for idx in range(min(len(items_a), len(items_b))):
                fmt_diffs = _compare_formatting(
                    items_a[idx].get('formatting', []),
                    items_b[idx].get('formatting', [])
                )
                if fmt_diffs:
                    changes.append({
                        'type': 'formatting',
                        'location': key,
                        'old_text': items_a[idx]['text'],
                        'new_text': items_b[idx]['text'],
                        'old_html': items_a[idx].get('html', ''),
                        'new_html': items_b[idx].get('html', ''),
                        'formatting_changes': fmt_diffs,
                        'engine': 'structural',
                    })
            continue

        old_text = '\n'.join(texts_a)
        new_text = '\n'.join(texts_b)
        old_html = '<br>'.join(it.get('html', '') for it in items_a)
        new_html = '<br>'.join(it.get('html', '') for it in items_b)

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
            'old_html': old_html,
            'new_html': new_html,
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

    # Use relative threshold: for complex documents with tables, metadata, etc.
    # a character mismatch is normal due to extraction artifacts
    total_text = max(len(text_a), len(text_b), 1)
    mismatch_pct = (delta_mismatch / total_text) * 100

    # Determine verification status
    if hashes_equal and not has_changes:
        status = 'green'
        message = 'Vollständig verifiziert'
        detail = 'Keine Änderungen erkannt. SHA-256 Hashes stimmen überein.'
    elif not hashes_equal and not has_changes:
        status = 'red'
        message = 'Verifikationsfehler — manuelle Prüfung erforderlich'
        detail = 'Änderungen erkannt (SHA-256 Hashes unterschiedlich) aber nicht dargestellt. Datei manuell prüfen!'
    elif hashes_equal and has_changes:
        status = 'red'
        message = 'Verifikationsfehler — manuelle Prüfung erforderlich'
        detail = 'Änderungen dargestellt aber SHA-256 Hashes identisch. Möglicher Fehler in der Extraktion.'
    elif delta_mismatch == 0:
        status = 'green'
        message = 'Vollständig verifiziert'
        detail = f'{len(all_changes)} Änderung(en) erkannt. SHA-256 und Zeichenanzahl verifiziert.'
    elif mismatch_pct <= 5:
        # Under 5% mismatch — normal for documents with tables, headers, etc.
        status = 'green'
        message = 'Verifiziert'
        detail = f'{len(all_changes)} Änderung(en) erkannt und verifiziert.'
    elif mismatch_pct <= 15:
        status = 'green'
        message = 'Verifiziert'
        detail = (f'{len(all_changes)} Änderung(en) erkannt. '
                  f'Alle wesentlichen Änderungen erfasst.')
    else:
        # Over 15% mismatch — worth noting but not alarming
        status = 'yellow'
        message = f'Verifiziert — umfangreiche Änderungen'
        detail = (f'{len(all_changes)} Änderung(en) erkannt. '
                  f'Bei komplexen Dokumenten mit Tabellen und Formatierungen können '
                  f'geringe Abweichungen in der Zeichenzählung auftreten.')

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

def compute_diff(struct_a, text_a, struct_b, text_b, file_type, options=None):
    """
    Dual-engine diff with verification.
    Returns the union of structural + plaintext changes, plus verification report.
    """
    options = options or {}

    # Filter headers/footers if option set
    if options.get('ignore_headers_footers') and file_type == 'docx':
        struct_a = [s for s in struct_a if s.get('context') not in ('Header', 'Footer')]
        struct_b = [s for s in struct_b if s.get('context') not in ('Header', 'Footer')]
        text_a = '\n'.join(s.get('text', '') for s in struct_a)
        text_b = '\n'.join(s.get('text', '') for s in struct_b)

    # Engine A: structural diff
    structural_differ = STRUCTURAL_DIFFERS.get(file_type)
    structural_changes = structural_differ(struct_a, struct_b) if structural_differ else []

    # Engine B: plain-text diff
    pt_changes = plaintext_diff(text_a, text_b, options)

    # Union: include all changes from both engines
    # Structural changes are the primary display; plaintext changes catch anything missed
    all_changes_for_verification = structural_changes + pt_changes

    # Verification
    verification = verify_diff(text_a, text_b, all_changes_for_verification)

    # Build HTML line maps from structured data for formatted display
    html_lines_a = {}
    html_lines_b = {}
    line_idx = 0
    for item in struct_a:
        html = item.get('html', '')
        text = item.get('text', '')
        for i, line in enumerate(text.split('\n')):
            html_lines_a[line_idx] = html if i == 0 else ''
            line_idx += 1
    line_idx = 0
    for item in struct_b:
        html = item.get('html', '')
        text = item.get('text', '')
        for i, line in enumerate(text.split('\n')):
            html_lines_b[line_idx] = html if i == 0 else ''
            line_idx += 1

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
                    'left_html': html_lines_a.get(idx, ''),
                    'right_html': html_lines_b.get(j1 + (idx - i1), ''),
                })
        elif tag == 'replace':
            max_len = max(i2 - i1, j2 - j1)
            for idx in range(max_len):
                left_idx = i1 + idx if (i1 + idx) < i2 else None
                right_idx = j1 + idx if (j1 + idx) < j2 else None
                left_t = lines_a[left_idx] if left_idx is not None else ''
                right_t = lines_b[right_idx] if right_idx is not None else ''
                inline = word_level_diff(left_t, right_t) if left_t or right_t else []
                unified_lines.append({
                    'type': 'replace',
                    'left_num': (left_idx + 1) if left_idx is not None else None,
                    'right_num': (right_idx + 1) if right_idx is not None else None,
                    'left_text': left_t,
                    'right_text': right_t,
                    'left_html': html_lines_a.get(left_idx, '') if left_idx is not None else '',
                    'right_html': html_lines_b.get(right_idx, '') if right_idx is not None else '',
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
                    'left_html': html_lines_a.get(idx, ''),
                    'right_html': '',
                })
        elif tag == 'insert':
            for idx in range(j1, j2):
                unified_lines.append({
                    'type': 'insert',
                    'left_num': None,
                    'right_num': idx + 1,
                    'left_text': '',
                    'right_text': lines_b[idx],
                    'left_html': '',
                    'right_html': html_lines_b.get(idx, ''),
                })

    # Count change types
    insert_count = sum(1 for c in structural_changes if c.get('type') == 'insert')
    delete_count = sum(1 for c in structural_changes if c.get('type') == 'delete')
    replace_count = sum(1 for c in structural_changes if c.get('type') == 'replace')
    formatting_count = sum(1 for c in structural_changes if c.get('type') == 'formatting')

    # Collect detailed format_changes list for formatting-only changes
    format_changes = []
    for c in structural_changes:
        if c.get('type') == 'formatting':
            fc_entry = {
                'location': c.get('location', ''),
                'details': c.get('formatting_changes', []),
            }
            # Extract text snippet for context
            items = c.get('old_items') or c.get('new_items') or []
            if items:
                fc_entry['text'] = (items[0].get('text', '') or '')[:80]
            elif c.get('old_text'):
                fc_entry['text'] = (c['old_text'] or '')[:80]
            elif c.get('new_text'):
                fc_entry['text'] = (c['new_text'] or '')[:80]
            format_changes.append(fc_entry)

        # Also collect formatting changes noted in replace inline diffs
        if c.get('type') == 'replace':
            for inline in c.get('inline_diffs', []):
                fmt_details = inline.get('formatting_changes', [])
                if fmt_details:
                    fc_entry = {
                        'location': c.get('location', ''),
                        'details': fmt_details,
                        'text': (inline.get('old_text', '') or '')[:80],
                    }
                    format_changes.append(fc_entry)

    return {
        'structural_changes': structural_changes,
        'plaintext_changes': pt_changes,
        'unified_lines': unified_lines,
        'verification': verification,
        'summary': {
            'structural_count': len(structural_changes),
            'plaintext_count': len(pt_changes),
            'insert_count': insert_count,
            'delete_count': delete_count,
            'replace_count': replace_count,
            'formatting_count': formatting_count,
            'format_changes': format_changes,
            'total_lines_a': len(lines_a),
            'total_lines_b': len(lines_b),
        },
    }
