"""
Text extraction for all supported file types.
Each extractor returns structured text and plain text for diff and verification.
"""
import os
import re


def extract_docx(filepath):
    """Extract text from DOCX files - paragraph-level structure."""
    from docx import Document
    doc = Document(filepath)
    paragraphs = []
    plain_parts = []

    for i, para in enumerate(doc.paragraphs):
        text = para.text
        paragraphs.append({
            'index': i,
            'text': text,
            'style': para.style.name if para.style else '',
        })
        plain_parts.append(text)

    # Also extract text from tables
    for table_idx, table in enumerate(doc.tables):
        for row_idx, row in enumerate(table.rows):
            for cell_idx, cell in enumerate(row.cells):
                cell_text = cell.text.strip()
                if cell_text:
                    paragraphs.append({
                        'index': len(paragraphs),
                        'text': cell_text,
                        'style': f'Table[{table_idx}].Row[{row_idx}].Cell[{cell_idx}]',
                    })
                    plain_parts.append(cell_text)

    # Extract from headers and footers
    for section in doc.sections:
        for header_footer in [section.header, section.footer]:
            if header_footer and header_footer.paragraphs:
                for para in header_footer.paragraphs:
                    text = para.text.strip()
                    if text:
                        paragraphs.append({
                            'index': len(paragraphs),
                            'text': text,
                            'style': 'Header/Footer',
                        })
                        plain_parts.append(text)

    plain_text = '\n'.join(plain_parts)
    return paragraphs, plain_text


def extract_xlsx(filepath):
    """Extract text from XLSX files - cell-level structure."""
    from openpyxl import load_workbook
    wb = load_workbook(filepath, data_only=True)
    cells = []
    plain_parts = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                val = cell.value
                if val is not None:
                    text = str(val)
                    coord = f"{sheet_name}!{cell.coordinate}"
                    cells.append({
                        'coord': coord,
                        'text': text,
                        'sheet': sheet_name,
                    })
                    plain_parts.append(f"{coord}={text}")

    plain_text = '\n'.join(plain_parts)
    return cells, plain_text


def extract_pptx(filepath):
    """Extract text from PPTX files - shape-level structure."""
    from pptx import Presentation
    prs = Presentation(filepath)
    elements = []
    plain_parts = []

    for slide_idx, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text
                    if text.strip():
                        elements.append({
                            'slide': slide_idx,
                            'shape': shape.name,
                            'text': text,
                        })
                        plain_parts.append(f"Slide{slide_idx}.{shape.name}: {text}")
            if shape.has_table:
                table = shape.table
                for row_idx, row in enumerate(table.rows):
                    for col_idx, cell in enumerate(row.cells):
                        text = cell.text.strip()
                        if text:
                            elements.append({
                                'slide': slide_idx,
                                'shape': f'{shape.name}.Table[{row_idx},{col_idx}]',
                                'text': text,
                            })
                            plain_parts.append(f"Slide{slide_idx}.{shape.name}[{row_idx},{col_idx}]: {text}")
        # Also extract notes
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            for para in slide.notes_slide.notes_text_frame.paragraphs:
                text = para.text.strip()
                if text:
                    elements.append({
                        'slide': slide_idx,
                        'shape': 'Notes',
                        'text': text,
                    })
                    plain_parts.append(f"Slide{slide_idx}.Notes: {text}")

    plain_text = '\n'.join(plain_parts)
    return elements, plain_text


def extract_pdf(filepath):
    """Extract text from PDF files using pdfplumber for accuracy."""
    import pdfplumber
    pages = []
    plain_parts = []

    with pdfplumber.open(filepath) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''
            pages.append({
                'page': page_num,
                'text': text,
            })
            plain_parts.append(text)

            # Also extract table data
            tables = page.extract_tables()
            for t_idx, table in enumerate(tables):
                for row in table:
                    row_text = ' | '.join(str(c) if c else '' for c in row)
                    pages.append({
                        'page': page_num,
                        'text': f'[Table {t_idx + 1}] {row_text}',
                    })
                    plain_parts.append(row_text)

    plain_text = '\n'.join(plain_parts)
    return pages, plain_text


EXTRACTORS = {
    'docx': extract_docx,
    'xlsx': extract_xlsx,
    'pptx': extract_pptx,
    'pdf': extract_pdf,
}


def extract(filepath, file_type):
    """Extract structured and plain text from a file."""
    ext = file_type.lower()
    if ext not in EXTRACTORS:
        raise ValueError(f"Unsupported file type: {ext}")
    return EXTRACTORS[ext](filepath)
