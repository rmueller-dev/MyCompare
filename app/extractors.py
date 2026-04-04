"""
Text extraction for all supported file types.
Each extractor returns structured data (with formatting), plain text, and formatting metadata.
"""
import os
import re
from html import escape


def _color_to_hex(color):
    """Convert various color objects to hex string."""
    if color is None:
        return None
    # python-docx RGBColor
    if hasattr(color, 'rgb') and color.rgb:
        return f'#{color.rgb}'
    if hasattr(color, 'theme_color'):
        return None  # theme colors need mapping, skip
    if isinstance(color, str) and len(color) == 6:
        return f'#{color}'
    return str(color) if color else None


def _emu_to_pt(emu):
    """Convert EMUs to points."""
    if emu is None:
        return None
    return round(emu / 12700, 1)


def _runs_to_html(runs):
    """Convert a list of runs (with formatting) to HTML with inline styles."""
    parts = []
    for run in runs:
        text = escape(run.text or '')
        if not text:
            continue
        styles = []
        if run.bold:
            styles.append('font-weight:bold')
        if run.italic:
            styles.append('font-style:italic')
        if run.underline:
            styles.append('text-decoration:underline')
        if hasattr(run, 'font'):
            font = run.font
            if font.strike:
                styles.append('text-decoration:line-through')
            if font.size:
                pt = _emu_to_pt(font.size)
                if pt:
                    styles.append(f'font-size:{pt}pt')
            if font.name:
                styles.append(f'font-family:{escape(font.name)}')
            color = font.color
            if color and color.rgb:
                styles.append(f'color:#{color.rgb}')
            if font.superscript:
                styles.append('vertical-align:super;font-size:smaller')
            if font.subscript:
                styles.append('vertical-align:sub;font-size:smaller')

        if styles:
            parts.append(f'<span style="{";".join(styles)}">{text}</span>')
        else:
            parts.append(text)
    return ''.join(parts)


def _runs_to_formatting(runs):
    """Extract formatting metadata from runs for diff comparison."""
    fmt_parts = []
    for run in runs:
        text = run.text or ''
        if not text:
            continue
        fmt = {
            'text': text,
            'bold': bool(run.bold),
            'italic': bool(run.italic),
            'underline': bool(run.underline),
        }
        if hasattr(run, 'font'):
            font = run.font
            fmt['strike'] = bool(font.strike)
            fmt['size'] = _emu_to_pt(font.size)
            fmt['font_name'] = font.name
            fmt['color'] = f'#{font.color.rgb}' if font.color and font.color.rgb else None
            fmt['superscript'] = bool(font.superscript)
            fmt['subscript'] = bool(font.subscript)
        fmt_parts.append(fmt)
    return fmt_parts


def _para_alignment_str(alignment):
    """Convert paragraph alignment to string."""
    if alignment is None:
        return None
    mapping = {0: 'left', 1: 'center', 2: 'right', 3: 'justify'}
    return mapping.get(int(alignment), str(alignment))


def _extract_xml_fields(para_element):
    """
    Extract field codes from paragraph XML (auto-numbering, cross-references, TOC, etc.).
    These are stored as w:fldChar / w:instrText in the XML, not visible via python-docx API.
    """
    from lxml import etree
    nsmap = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    fields = []

    # Simple fields (w:fldSimple)
    for fld in para_element.findall('.//w:fldSimple', nsmap):
        instr = fld.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}instr', '')
        display = ''.join(t.text or '' for t in fld.findall('.//w:t', nsmap))
        if instr.strip():
            fields.append({'instruction': instr.strip(), 'display': display})

    # Complex fields (w:fldChar begin...w:instrText...w:fldChar end)
    in_field = False
    current_instr = []
    current_display = []
    for child in para_element.iter():
        tag = etree.QName(child.tag).localname if '}' in child.tag else child.tag
        if tag == 'fldChar':
            fld_type = child.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fldCharType', '')
            if fld_type == 'begin':
                in_field = True
                current_instr = []
                current_display = []
            elif fld_type == 'separate':
                pass  # after this comes display text
            elif fld_type == 'end':
                if current_instr:
                    fields.append({
                        'instruction': ' '.join(current_instr).strip(),
                        'display': ''.join(current_display),
                    })
                in_field = False
                current_instr = []
                current_display = []
        elif tag == 'instrText' and in_field:
            current_instr.append(child.text or '')
        elif tag == 't' and in_field:
            current_display.append(child.text or '')

    return fields


def _extract_numbering_info(para, doc):
    """Extract auto-numbering information from paragraph."""
    try:
        pPr = para._element.find(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr'
        )
        if pPr is None:
            return None
        numPr = pPr.find(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr'
        )
        if numPr is None:
            return None
        ilvl = numPr.find(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ilvl'
        )
        numId = numPr.find(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numId'
        )
        level = ilvl.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') if ilvl is not None else '0'
        num_id = numId.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') if numId is not None else None

        return {
            'numId': num_id,
            'level': int(level) if level else 0,
        }
    except Exception:
        return None


def _extract_bookmarks(para_element):
    """Extract bookmarks from paragraph XML."""
    nsmap = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    bookmarks = []
    for bm in para_element.findall('.//w:bookmarkStart', nsmap):
        name = bm.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name', '')
        if name and not name.startswith('_'):  # Skip internal bookmarks
            bookmarks.append(name)
    return bookmarks


def _extract_comments(doc_element):
    """Extract all comments from the DOCX comments part."""
    from lxml import etree
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    nsmap = {'w': W}
    comments = {}

    # Access the comments part via the package
    try:
        comment_part = None
        for rel in doc_element.part.rels.values():
            if 'comments' in rel.reltype:
                comment_part = rel.target_part
                break
        if comment_part is None:
            return comments

        root = etree.fromstring(comment_part.blob)
        for comment_el in root.findall(f'{{{W}}}comment'):
            cid = comment_el.get(f'{{{W}}}id', '')
            author = comment_el.get(f'{{{W}}}author', '')
            date = comment_el.get(f'{{{W}}}date', '')
            text_parts = []
            for p in comment_el.findall(f'{{{W}}}p'):
                for t in p.findall(f'.//{{{W}}}t'):
                    if t.text:
                        text_parts.append(t.text)
            comments[cid] = {
                'id': cid,
                'author': author,
                'date': date,
                'text': ' '.join(text_parts),
            }
    except Exception:
        pass
    return comments


def _extract_footnotes(doc_element):
    """Extract all footnotes from the DOCX footnotes part."""
    from lxml import etree
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    footnotes = {}
    try:
        fn_part = None
        for rel in doc_element.part.rels.values():
            if 'footnotes' in rel.reltype:
                fn_part = rel.target_part
                break
        if fn_part is None:
            return footnotes

        root = etree.fromstring(fn_part.blob)
        for fn_el in root.findall(f'{{{W}}}footnote'):
            fid = fn_el.get(f'{{{W}}}id', '')
            fn_type = fn_el.get(f'{{{W}}}type', '')
            if fn_type in ('separator', 'continuationSeparator'):
                continue
            text_parts = []
            for p in fn_el.findall(f'{{{W}}}p'):
                for t in p.findall(f'.//{{{W}}}t'):
                    if t.text:
                        text_parts.append(t.text)
            if text_parts:
                footnotes[fid] = ' '.join(text_parts)
    except Exception:
        pass
    return footnotes


def _extract_endnotes(doc_element):
    """Extract all endnotes from the DOCX endnotes part."""
    from lxml import etree
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    endnotes = {}
    try:
        en_part = None
        for rel in doc_element.part.rels.values():
            if 'endnotes' in rel.reltype:
                en_part = rel.target_part
                break
        if en_part is None:
            return endnotes

        root = etree.fromstring(en_part.blob)
        for en_el in root.findall(f'{{{W}}}endnote'):
            eid = en_el.get(f'{{{W}}}id', '')
            en_type = en_el.get(f'{{{W}}}type', '')
            if en_type in ('separator', 'continuationSeparator'):
                continue
            text_parts = []
            for p in en_el.findall(f'{{{W}}}p'):
                for t in p.findall(f'.//{{{W}}}t'):
                    if t.text:
                        text_parts.append(t.text)
            if text_parts:
                endnotes[eid] = ' '.join(text_parts)
    except Exception:
        pass
    return endnotes


def _extract_comment_refs(para_element):
    """Extract comment reference IDs from a paragraph."""
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    refs = []
    for cr in para_element.findall(f'.//{{{W}}}commentRangeStart'):
        cid = cr.get(f'{{{W}}}id', '')
        if cid:
            refs.append(cid)
    return refs


def _extract_footnote_refs(para_element):
    """Extract footnote/endnote reference IDs from a paragraph."""
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    fn_refs = []
    en_refs = []
    for ref in para_element.findall(f'.//{{{W}}}footnoteReference'):
        fid = ref.get(f'{{{W}}}id', '')
        if fid:
            fn_refs.append(fid)
    for ref in para_element.findall(f'.//{{{W}}}endnoteReference'):
        eid = ref.get(f'{{{W}}}id', '')
        if eid:
            en_refs.append(eid)
    return fn_refs, en_refs


def _extract_para_images(para_element, doc_part):
    """
    Extract image references from a paragraph element.
    Looks for w:drawing and w:pict elements that embed images via relationships.
    Returns a list of image filenames referenced in this paragraph.
    """
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
    import os

    image_names = []

    # Look for w:drawing > wp:inline or wp:anchor > a:graphic > a:graphicData > a:blip
    for drawing in para_element.findall(f'.//{{{W}}}drawing'):
        for blip in drawing.findall(f'.//{{{A}}}blip'):
            embed_id = blip.get(f'{{{R}}}embed')
            if embed_id and embed_id in doc_part.rels:
                rel = doc_part.rels[embed_id]
                if hasattr(rel, 'target_ref'):
                    image_names.append(os.path.basename(rel.target_ref))
                elif hasattr(rel, 'target_partname'):
                    image_names.append(os.path.basename(str(rel.target_partname)))

    # Look for w:pict > v:imagedata (older VML format)
    VML = 'urn:schemas-microsoft-com:vml'
    for pict in para_element.findall(f'.//{{{W}}}pict'):
        for imagedata in pict.findall(f'.//{{{VML}}}imagedata'):
            embed_id = imagedata.get(f'{{{R}}}id')
            if embed_id and embed_id in doc_part.rels:
                rel = doc_part.rels[embed_id]
                if hasattr(rel, 'target_ref'):
                    image_names.append(os.path.basename(rel.target_ref))
                elif hasattr(rel, 'target_partname'):
                    image_names.append(os.path.basename(str(rel.target_partname)))

    return image_names


def extract_docx(filepath):
    """Extract text with formatting, fields, numbering, cross-refs, TOC, comments,
    footnotes, endnotes, XE/TA/TC index entries, and embedded images from DOCX files."""
    from docx import Document
    doc = Document(filepath)
    paragraphs = []
    plain_parts = []

    # Extract document-level comments, footnotes, endnotes
    all_comments = _extract_comments(doc.element)
    all_footnotes = _extract_footnotes(doc.element)
    all_endnotes = _extract_endnotes(doc.element)

    # Get the document part for resolving image relationships
    doc_part = doc.part

    def process_para(para, context=''):
        text = para.text
        html = _runs_to_html(para.runs)
        formatting = _runs_to_formatting(para.runs)
        alignment = _para_alignment_str(para.alignment)
        style_name = para.style.name if para.style else ''

        # Extract fields (cross-references, TOC entries, page numbers, auto-numbering display)
        fields = _extract_xml_fields(para._element)

        # Extract numbering info
        numbering = _extract_numbering_info(para, doc)

        # Extract bookmarks
        bookmarks = _extract_bookmarks(para._element)

        # Extract comment references for this paragraph
        comment_refs = _extract_comment_refs(para._element)
        para_comments = []
        for cid in comment_refs:
            if cid in all_comments:
                para_comments.append(all_comments[cid])

        # Extract footnote/endnote references for this paragraph
        fn_refs, en_refs = _extract_footnote_refs(para._element)
        para_footnotes = []
        for fid in fn_refs:
            if fid in all_footnotes:
                para_footnotes.append({'id': fid, 'text': all_footnotes[fid]})
        para_endnotes = []
        for eid in en_refs:
            if eid in all_endnotes:
                para_endnotes.append({'id': eid, 'text': all_endnotes[eid]})

        # Extract embedded image references for this paragraph
        para_image_names = _extract_para_images(para._element, doc_part)

        # Enrich text with field information for diff detection
        field_text_parts = []
        for f in fields:
            instr = f['instruction'].upper()
            display = f['display']
            if 'XE' in instr:
                field_text_parts.append(f'[Index-Eintrag: {f["instruction"]}]')
            elif 'TA' in instr:
                field_text_parts.append(f'[Rechtsquellenverzeichnis: {f["instruction"]}]')
            elif 'TC' in instr:
                field_text_parts.append(f'[Verzeichniseintrag: {f["instruction"]}]')
            elif 'TOC' in instr:
                field_text_parts.append(f'[Inhaltsverzeichnis: {f["instruction"]}]')
            elif 'TOA' in instr:
                field_text_parts.append(f'[Rechtsquellenverzeichnis: {f["instruction"]}]')
            elif 'INDEX' in instr:
                field_text_parts.append(f'[Stichwortverzeichnis: {f["instruction"]}]')
            elif 'REF' in instr:
                field_text_parts.append(f'[Querverweis: {f["instruction"]} → "{display}"]')
            elif 'PAGEREF' in instr:
                field_text_parts.append(f'[Seitenverweis: {f["instruction"]} → "{display}"]')
            elif 'NOTEREF' in instr:
                field_text_parts.append(f'[Fußnotenverweis: {f["instruction"]} → "{display}"]')
            elif 'PAGE' in instr:
                field_text_parts.append(f'[Seitenzahl: {display}]')
            elif 'SEQ' in instr:
                field_text_parts.append(f'[Nummerierung: {f["instruction"]} → "{display}"]')
            elif 'HYPERLINK' in instr:
                field_text_parts.append(f'[Link: {f["instruction"]}]')
            elif 'AUTOTEXT' in instr or 'AUTOTEXTLIST' in instr:
                field_text_parts.append(f'[AutoText: {f["instruction"]}]')
            elif 'CITATION' in instr or 'BIBLIOGRAPHY' in instr:
                field_text_parts.append(f'[Zitat: {f["instruction"]}]')
            elif 'IF' in instr:
                field_text_parts.append(f'[Bedingungsfeld: {f["instruction"]}]')
            elif 'MERGEFIELD' in instr:
                field_text_parts.append(f'[Seriendruckfeld: {f["instruction"]}]')
            elif 'DOCPROPERTY' in instr or 'INFO' in instr:
                field_text_parts.append(f'[Dokumenteigenschaft: {f["instruction"]}]')
            elif 'DATE' in instr or 'TIME' in instr:
                field_text_parts.append(f'[Datum/Zeit: {f["instruction"]} → "{display}"]')
            elif 'NUMPAGES' in instr or 'SECTIONPAGES' in instr:
                field_text_parts.append(f'[Seitenanzahl: {display}]')
            elif 'STYLEREF' in instr:
                field_text_parts.append(f'[Formatvorlagenverweis: {f["instruction"]} → "{display}"]')
            else:
                field_text_parts.append(f'[Feld: {f["instruction"]} → "{display}"]')

        # Add comment text to enriched text for diff
        comment_text_parts = []
        for c in para_comments:
            comment_text_parts.append(f'[Kommentar ({c["author"]}): {c["text"]}]')

        # Add footnote/endnote text
        fn_text_parts = []
        for fn in para_footnotes:
            fn_text_parts.append(f'[Fußnote {fn["id"]}: {fn["text"]}]')
        for en in para_endnotes:
            fn_text_parts.append(f'[Endnote {en["id"]}: {en["text"]}]')

        # Add numbering prefix to HTML for visual display
        num_prefix = ''
        if numbering:
            num_prefix = f'<span style="color:#666;margin-right:4px">[Ebene {numbering["level"]}]</span>'

        # Add field annotations to HTML
        field_html = ''
        all_annotations = field_text_parts + comment_text_parts + fn_text_parts
        if all_annotations:
            field_tags = ' '.join(
                f'<span style="background:#e0e7ff;color:#3730a3;font-size:0.75em;padding:1px 4px;border-radius:3px;margin-left:2px">{escape(ft)}</span>'
                for ft in all_annotations
            )
            field_html = f' {field_tags}'

        # Add comment bubbles to HTML
        comment_html = ''
        if para_comments:
            comment_tags = ' '.join(
                f'<span style="background:#fef3c7;color:#92400e;font-size:0.75em;padding:2px 6px;border-radius:3px;border:1px solid #f59e0b;margin-left:4px" title="{escape(c["text"])}">'
                f'💬 {escape(c["author"])}: {escape(c["text"][:60])}</span>'
                for c in para_comments
            )
            comment_html = f' {comment_tags}'

        # Add footnote/endnote markers to HTML
        fn_html = ''
        if para_footnotes or para_endnotes:
            fn_tags = []
            for fn in para_footnotes:
                fn_tags.append(
                    f'<span style="background:#dbeafe;color:#1e40af;font-size:0.75em;padding:2px 6px;border-radius:3px;border:1px solid #3b82f6;margin-left:4px"'
                    f' title="{escape(fn["text"])}">Fn{fn["id"]}</span>'
                )
            for en in para_endnotes:
                fn_tags.append(
                    f'<span style="background:#ede9fe;color:#5b21b6;font-size:0.75em;padding:2px 6px;border-radius:3px;border:1px solid #7c3aed;margin-left:4px"'
                    f' title="{escape(en["text"])}">En{en["id"]}</span>'
                )
            fn_html = ' ' + ' '.join(fn_tags)

        # Build image text markers for enriched text and HTML
        image_text_parts = []
        image_html = ''
        for img_name in para_image_names:
            image_text_parts.append(f'[Bild: {img_name}]')
        if image_text_parts:
            img_tags = ' '.join(
                f'<span style="background:#fce4ec;color:#c62828;font-size:0.75em;padding:1px 4px;border-radius:3px;margin-left:2px">{escape(it)}</span>'
                for it in image_text_parts
            )
            image_html = f' {img_tags}'

        # Wrap html in alignment div if needed
        full_html = f'{num_prefix}{html}{field_html}{comment_html}{fn_html}{image_html}'
        if alignment and alignment != 'left':
            full_html = f'<div style="text-align:{alignment}">{full_html}</div>'

        # Build enriched plain text for comparison (includes field info, comments, footnotes, images)
        enriched_text = text
        all_extra = field_text_parts + comment_text_parts + fn_text_parts + image_text_parts
        if all_extra:
            enriched_text = text + ' ' + ' '.join(all_extra)

        # Compute formatting_key for quick formatting-only change detection
        fmt_key_parts = []
        for f in formatting:
            for k, v in sorted(f.items()):
                if k != 'text' and v:
                    fmt_key_parts.append(f'{k}={v}')
        if alignment:
            fmt_key_parts.append(f'align={alignment}')
        if style_name:
            fmt_key_parts.append(f'style={style_name}')
        formatting_key = ';'.join(fmt_key_parts)

        entry = {
            'index': len(paragraphs),
            'text': text,
            'enriched_text': enriched_text,
            'html': full_html,
            'formatting': formatting,
            'formatting_key': formatting_key,
            'alignment': alignment,
            'style': style_name,
            'context': context,
            'fields': fields,
            'numbering': numbering,
            'bookmarks': bookmarks,
            'comments': para_comments,
            'footnotes': para_footnotes,
            'endnotes': para_endnotes,
            'images': para_image_names,
        }
        paragraphs.append(entry)
        # Use enriched text for plain text so field/comment/footnote changes are detected
        plain_parts.append(enriched_text)

    for para in doc.paragraphs:
        process_para(para, 'body')

    # Tables
    for table_idx, table in enumerate(doc.tables):
        for row_idx, row in enumerate(table.rows):
            for cell_idx, cell in enumerate(row.cells):
                for para in cell.paragraphs:
                    if para.text.strip():
                        process_para(para, f'Table[{table_idx}].Row[{row_idx}].Cell[{cell_idx}]')

    # Headers and footers
    for section in doc.sections:
        for hf_name, hf in [('Header', section.header), ('Footer', section.footer)]:
            if hf and hf.paragraphs:
                for para in hf.paragraphs:
                    if para.text.strip():
                        process_para(para, hf_name)

    # Add standalone footnotes/endnotes that aren't referenced in body
    for fid, fn_text in all_footnotes.items():
        plain_parts.append(f'[Fußnote {fid}: {fn_text}]')
    for eid, en_text in all_endnotes.items():
        plain_parts.append(f'[Endnote {eid}: {en_text}]')

    plain_text = '\n'.join(plain_parts)
    return paragraphs, plain_text


def extract_xlsx(filepath):
    """Extract text with formatting from XLSX files."""
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = load_workbook(filepath, data_only=False)
    wb_data = load_workbook(filepath, data_only=True)
    cells = []
    plain_parts = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        ws_data = wb_data[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                val = cell.value
                # Also get computed value from data_only workbook
                data_cell = ws_data[cell.coordinate]
                display_val = data_cell.value if data_cell.value is not None else val

                if val is not None or display_val is not None:
                    text = str(display_val if display_val is not None else val)
                    coord = f"{sheet_name}!{cell.coordinate}"

                    # Extract formatting
                    fmt = {}
                    font = cell.font
                    if font:
                        fmt['bold'] = bool(font.bold)
                        fmt['italic'] = bool(font.italic)
                        fmt['underline'] = font.underline if font.underline and font.underline != 'none' else None
                        fmt['strike'] = bool(font.strikethrough)
                        fmt['font_name'] = font.name
                        fmt['font_size'] = font.size
                        if font.color and font.color.rgb and str(font.color.rgb) != '00000000':
                            fmt['color'] = f'#{font.color.rgb}'
                        else:
                            fmt['color'] = None

                    fill = cell.fill
                    if fill and fill.fgColor and fill.fgColor.rgb and str(fill.fgColor.rgb) not in ('00000000', '0'):
                        fmt['bg_color'] = f'#{fill.fgColor.rgb}'
                    else:
                        fmt['bg_color'] = None

                    alignment = cell.alignment
                    if alignment:
                        fmt['align'] = alignment.horizontal
                    fmt['number_format'] = cell.number_format if cell.number_format != 'General' else None

                    # Build HTML
                    styles = []
                    if fmt.get('bold'):
                        styles.append('font-weight:bold')
                    if fmt.get('italic'):
                        styles.append('font-style:italic')
                    if fmt.get('underline'):
                        styles.append('text-decoration:underline')
                    if fmt.get('strike'):
                        styles.append('text-decoration:line-through')
                    if fmt.get('font_name'):
                        styles.append(f'font-family:{escape(fmt["font_name"])}')
                    if fmt.get('font_size'):
                        styles.append(f'font-size:{fmt["font_size"]}pt')
                    if fmt.get('color'):
                        styles.append(f'color:{fmt["color"]}')
                    if fmt.get('bg_color'):
                        styles.append(f'background-color:{fmt["bg_color"]}')

                    html = f'<span style="{";".join(styles)}">{escape(text)}</span>' if styles else escape(text)

                    # Serialize formatting for comparison
                    fmt_key = ';'.join(f'{k}={v}' for k, v in sorted(fmt.items()) if v)

                    cells.append({
                        'coord': coord,
                        'text': text,
                        'html': html,
                        'formatting': fmt,
                        'formatting_key': fmt_key,
                        'sheet': sheet_name,
                        'formula': str(val) if isinstance(val, str) and val.startswith('=') else None,
                    })
                    plain_parts.append(f"{coord}={text}")

    plain_text = '\n'.join(plain_parts)
    return cells, plain_text


def extract_pptx(filepath):
    """Extract text with formatting from PPTX files."""
    from pptx import Presentation
    from pptx.util import Pt, Emu

    prs = Presentation(filepath)
    elements = []
    plain_parts = []

    for slide_idx, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text
                    if not text.strip():
                        continue

                    # Build HTML from runs
                    html_parts = []
                    fmt_parts = []
                    for run in para.runs:
                        run_text = run.text or ''
                        if not run_text:
                            continue
                        styles = []
                        fmt = {'text': run_text}

                        font = run.font
                        if font.bold:
                            styles.append('font-weight:bold')
                            fmt['bold'] = True
                        if font.italic:
                            styles.append('font-style:italic')
                            fmt['italic'] = True
                        if font.underline:
                            styles.append('text-decoration:underline')
                            fmt['underline'] = True
                        if font.size:
                            pt = _emu_to_pt(font.size)
                            if pt:
                                styles.append(f'font-size:{pt}pt')
                                fmt['size'] = pt
                        if font.name:
                            styles.append(f'font-family:{escape(font.name)}')
                            fmt['font_name'] = font.name
                        if font.color and font.color.rgb:
                            styles.append(f'color:#{font.color.rgb}')
                            fmt['color'] = f'#{font.color.rgb}'

                        if styles:
                            html_parts.append(f'<span style="{";".join(styles)}">{escape(run_text)}</span>')
                        else:
                            html_parts.append(escape(run_text))
                        fmt_parts.append(fmt)

                    # Paragraph alignment
                    alignment = None
                    if para.alignment is not None:
                        align_map = {0: 'left', 1: 'center', 2: 'right', 3: 'justify'}
                        alignment = align_map.get(int(para.alignment))

                    html = ''.join(html_parts)
                    if alignment and alignment != 'left':
                        html = f'<div style="text-align:{alignment}">{html}</div>'

                    elements.append({
                        'slide': slide_idx,
                        'shape': shape.name,
                        'text': text,
                        'html': html,
                        'formatting': fmt_parts,
                        'alignment': alignment,
                    })
                    plain_parts.append(f"Slide{slide_idx}.{shape.name}: {text}")

            if shape.has_table:
                table = shape.table
                for row_idx, row in enumerate(table.rows):
                    for col_idx, cell in enumerate(row.cells):
                        text = cell.text.strip()
                        if text:
                            # Extract formatting from cell paragraphs
                            cell_html_parts = []
                            cell_fmt = []
                            for para in cell.text_frame.paragraphs:
                                for run in para.runs:
                                    run_text = run.text or ''
                                    if not run_text:
                                        continue
                                    styles = []
                                    fmt = {'text': run_text}
                                    font = run.font
                                    if font.bold:
                                        styles.append('font-weight:bold')
                                        fmt['bold'] = True
                                    if font.italic:
                                        styles.append('font-style:italic')
                                        fmt['italic'] = True
                                    if font.size:
                                        pt = _emu_to_pt(font.size)
                                        if pt:
                                            styles.append(f'font-size:{pt}pt')
                                            fmt['size'] = pt
                                    if styles:
                                        cell_html_parts.append(f'<span style="{";".join(styles)}">{escape(run_text)}</span>')
                                    else:
                                        cell_html_parts.append(escape(run_text))
                                    cell_fmt.append(fmt)

                            elements.append({
                                'slide': slide_idx,
                                'shape': f'{shape.name}.Table[{row_idx},{col_idx}]',
                                'text': text,
                                'html': ''.join(cell_html_parts) or escape(text),
                                'formatting': cell_fmt,
                            })
                            plain_parts.append(f"Slide{slide_idx}.{shape.name}[{row_idx},{col_idx}]: {text}")

        # Notes
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            for para in slide.notes_slide.notes_text_frame.paragraphs:
                text = para.text.strip()
                if text:
                    elements.append({
                        'slide': slide_idx,
                        'shape': 'Notes',
                        'text': text,
                        'html': escape(text),
                        'formatting': [{'text': text}],
                    })
                    plain_parts.append(f"Slide{slide_idx}.Notes: {text}")

    plain_text = '\n'.join(plain_parts)
    return elements, plain_text


def _ocr_page_image(page):
    """Apply OCR to a PDF page that appears to be image-based (scanned).
    Returns extracted text or empty string if OCR is not available."""
    try:
        import pytesseract
        from PIL import Image
        import io

        # Convert pdfplumber page to image
        img = page.to_image(resolution=300)
        # img.original is a PIL Image
        pil_img = img.original
        text = pytesseract.image_to_string(pil_img, lang='deu+eng')
        return text.strip()
    except ImportError:
        return ''  # pytesseract not installed
    except Exception:
        return ''


def extract_pdf(filepath):
    """Extract text from PDF files using pdfplumber with font info.
    Automatically applies OCR for scanned/image-based pages when pytesseract is available."""
    import pdfplumber
    pages = []
    plain_parts = []

    with pdfplumber.open(filepath) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''

            # If page has very little text but has images, try OCR
            chars = page.chars or []
            is_scanned = len(chars) < 10 and len(page.images or []) > 0
            if is_scanned and not text.strip():
                ocr_text = _ocr_page_image(page)
                if ocr_text:
                    text = f'[OCR] {ocr_text}'

            # Extract character-level font info for formatting detection
            font_info = {}
            for char in chars:
                font_name = char.get('fontname', '')
                font_size = round(char.get('size', 0), 1)
                key = f"{font_name}@{font_size}"
                font_info[key] = font_info.get(key, 0) + 1

            # Build HTML with basic font info annotations
            html_lines = []
            for line in text.split('\n'):
                html_lines.append(escape(line))
            html = '<br>'.join(html_lines)

            pages.append({
                'page': page_num,
                'text': text,
                'html': html,
                'font_info': font_info,
                'ocr': is_scanned,
            })
            plain_parts.append(text)

            # Tables
            tables = page.extract_tables()
            for t_idx, table in enumerate(tables):
                for row in table:
                    row_text = ' | '.join(str(c) if c else '' for c in row)
                    pages.append({
                        'page': page_num,
                        'text': f'[Table {t_idx + 1}] {row_text}',
                        'html': f'<em>[Tabelle {t_idx + 1}]</em> {escape(row_text)}',
                        'font_info': {},
                    })
                    plain_parts.append(row_text)

    plain_text = '\n'.join(plain_parts)
    return pages, plain_text


def extract_rtf(filepath):
    """Extract text from RTF files."""
    import re
    with open(filepath, 'rb') as f:
        raw = f.read()
    # Try to decode as UTF-8, fallback to latin-1
    try:
        content = raw.decode('utf-8')
    except UnicodeDecodeError:
        content = raw.decode('latin-1')

    # Strip RTF control words and groups
    text = re.sub(r'\\[a-z]+\d*\s?', '', content)
    text = re.sub(r'[{}]', '', text)
    text = re.sub(r'\\\'[0-9a-fA-F]{2}', '', text)  # hex chars
    text = text.strip()

    paragraphs = []
    plain_parts = []
    for i, line in enumerate(text.split('\n')):
        line = line.strip()
        if line:
            paragraphs.append({
                'index': i,
                'text': line,
                'html': escape(line),
                'formatting': [{'text': line}],
            })
            plain_parts.append(line)

    return paragraphs, '\n'.join(plain_parts)


def extract_html(filepath):
    """Extract text from HTML files using basic parsing."""
    import re as _re
    # Try UTF-8, then latin-1
    for enc in ['utf-8', 'utf-8-sig', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        content = ''

    # Remove script and style blocks
    content = _re.sub(r'<script[^>]*>.*?</script>', '', content, flags=_re.DOTALL | _re.IGNORECASE)
    content = _re.sub(r'<style[^>]*>.*?</style>', '', content, flags=_re.DOTALL | _re.IGNORECASE)

    # Extract text from remaining HTML
    # Replace block elements with newlines
    for tag in ('p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'td', 'th'):
        content = _re.sub(rf'</?{tag}[^>]*>', '\n', content, flags=_re.IGNORECASE)

    # Strip remaining tags
    text = _re.sub(r'<[^>]+>', '', content)
    # Decode HTML entities
    from html import unescape
    text = unescape(text)
    # Clean up whitespace
    lines = [l.strip() for l in text.split('\n')]
    lines = [l for l in lines if l]  # remove empty lines

    paragraphs = []
    plain_parts = []
    for i, line in enumerate(lines):
        paragraphs.append({
            'index': i,
            'text': line,
            'html': escape(line),
            'formatting': [{'text': line}],
        })
        plain_parts.append(line)

    return paragraphs, '\n'.join(plain_parts)


def extract_txt(filepath):
    """Extract text from plain text files."""
    # Try UTF-8, then latin-1
    for enc in ['utf-8', 'utf-8-sig', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        content = ''

    paragraphs = []
    plain_parts = []
    for i, line in enumerate(content.split('\n')):
        paragraphs.append({
            'index': i,
            'text': line,
            'html': escape(line),
            'formatting': [{'text': line}],
        })
        plain_parts.append(line)

    return paragraphs, '\n'.join(plain_parts)


EXTRACTORS = {
    'docx': extract_docx,
    'xlsx': extract_xlsx,
    'pptx': extract_pptx,
    'pdf': extract_pdf,
    'rtf': extract_rtf,
    'txt': extract_txt,
    'html': extract_html,
    'htm': extract_html,
}


def extract(filepath, file_type):
    """Extract structured and plain text from a file."""
    ext = file_type.lower()
    if ext not in EXTRACTORS:
        raise ValueError(f"Unsupported file type: {ext}")
    return EXTRACTORS[ext](filepath)
