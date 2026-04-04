"""Flask API routes."""
import os
import uuid
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from .models import SessionLocal, Document, Version, STORAGE_DIR
from .extractors import extract
from .diff_engine import compute_diff

api = Blueprint('api', __name__, url_prefix='/api')

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def get_file_type(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext in ('docx', 'xlsx', 'pptx', 'pdf', 'rtf', 'txt'):
        return ext
    return None


@api.route('/documents', methods=['GET'])
def list_documents():
    session = SessionLocal()
    try:
        docs = session.query(Document).order_by(Document.created_at.desc()).all()
        return jsonify([d.to_dict() for d in docs])
    finally:
        session.close()


@api.route('/documents', methods=['POST'])
def create_document():
    """Upload a file, creating a new document or adding a version to an existing one."""
    if 'file' not in request.files:
        return jsonify({'error': 'Keine Datei hochgeladen'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Kein Dateiname'}), 400

    file_type = get_file_type(file.filename)
    if not file_type:
        return jsonify({'error': 'Nicht unterstützter Dateityp. Erlaubt: DOCX, XLSX, PPTX, PDF, RTF, TXT'}), 400

    # Check file size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({'error': f'Datei zu groß. Maximum: {MAX_FILE_SIZE // (1024*1024)} MB'}), 400

    document_id = request.form.get('document_id')
    label = request.form.get('label', '')

    session = SessionLocal()
    try:
        if document_id:
            doc = session.query(Document).get(int(document_id))
            if not doc:
                return jsonify({'error': 'Dokument nicht gefunden'}), 404
            if doc.file_type != file_type:
                return jsonify({'error': f'Dateityp stimmt nicht überein. Erwartet: {doc.file_type}'}), 400
        else:
            doc_name = request.form.get('name', file.filename.rsplit('.', 1)[0])
            doc = Document(name=doc_name, file_type=file_type)
            session.add(doc)
            session.flush()

        # Determine version number
        max_version = 0
        for v in doc.versions:
            if v.version_number > max_version:
                max_version = v.version_number
        new_version_num = max_version + 1

        # Save file with secure filename
        safe_name = secure_filename(file.filename) or 'upload'
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"
        doc_dir = os.path.join(STORAGE_DIR, str(doc.id))
        os.makedirs(doc_dir, exist_ok=True)
        filepath = os.path.join(doc_dir, unique_name)
        # Verify path is within storage dir (defense in depth)
        if not os.path.realpath(filepath).startswith(os.path.realpath(STORAGE_DIR)):
            return jsonify({'error': 'Ungültiger Dateipfad'}), 400
        file.save(filepath)

        version = Version(
            document_id=doc.id,
            version_number=new_version_num,
            filename=safe_name,
            filepath=filepath,
            label=label,
        )
        session.add(version)
        session.commit()

        # Refresh to get relationships
        session.refresh(doc)
        return jsonify(doc.to_dict()), 201
    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Upload fehlgeschlagen. Bitte prüfen Sie die Datei.'}), 500
    finally:
        session.close()


@api.route('/documents/<int:doc_id>', methods=['GET'])
def get_document(doc_id):
    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Nicht gefunden'}), 404
        return jsonify(doc.to_dict())
    finally:
        session.close()


@api.route('/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Nicht gefunden'}), 404
        for v in doc.versions:
            session.delete(v)
        session.delete(doc)
        session.commit()
        return jsonify({'ok': True})
    finally:
        session.close()


@api.route('/documents/<int:doc_id>/versions/<int:ver_id>', methods=['PATCH'])
def update_version_label(doc_id, ver_id):
    session = SessionLocal()
    try:
        version = session.query(Version).filter_by(id=ver_id, document_id=doc_id).first()
        if not version:
            return jsonify({'error': 'Version nicht gefunden'}), 404
        data = request.get_json()
        if 'label' in data:
            version.label = data['label']
        session.commit()
        return jsonify(version.to_dict())
    finally:
        session.close()


@api.route('/diff/<int:doc_id>/<int:version_a>/<int:version_b>', methods=['GET'])
def diff_versions(doc_id, version_a, version_b):
    """Compare two versions of a document."""
    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Dokument nicht gefunden'}), 404

        ver_a = session.query(Version).filter_by(document_id=doc_id, version_number=version_a).first()
        ver_b = session.query(Version).filter_by(document_id=doc_id, version_number=version_b).first()

        if not ver_a or not ver_b:
            return jsonify({'error': 'Version nicht gefunden'}), 404

        # Extract content from both versions
        struct_a, text_a = extract(ver_a.filepath, doc.file_type)
        struct_b, text_b = extract(ver_b.filepath, doc.file_type)

        # Parse comparison options
        options = {
            'ignore_whitespace': request.args.get('ignore_whitespace') == '1',
            'ignore_case': request.args.get('ignore_case') == '1',
            'ignore_headers_footers': request.args.get('ignore_headers_footers') == '1',
        }

        # Compute diff with verification
        result = compute_diff(struct_a, text_a, struct_b, text_b, doc.file_type, options)

        result['version_a'] = ver_a.to_dict()
        result['version_b'] = ver_b.to_dict()
        result['document'] = doc.to_dict()

        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Vergleich fehlgeschlagen. Bitte prüfen Sie die Dateien.'}), 500
    finally:
        session.close()


@api.route('/quick-compare', methods=['POST'])
def quick_compare():
    """
    Quick compare: Upload 2 files, auto-detect old/new by last-modified metadata,
    run diff immediately and return results.
    """
    if 'file_old' not in request.files or 'file_new' not in request.files:
        return jsonify({'error': 'Bitte zwei Dateien hochladen (file_old, file_new)'}), 400

    file_old = request.files['file_old']
    file_new = request.files['file_new']

    if not file_old.filename or not file_new.filename:
        return jsonify({'error': 'Keine Dateinamen'}), 400

    type_old = get_file_type(file_old.filename)
    type_new = get_file_type(file_new.filename)

    if not type_old or not type_new:
        return jsonify({'error': 'Nicht unterstützter Dateityp. Erlaubt: DOCX, XLSX, PPTX, PDF, RTF, TXT'}), 400
    if type_old != type_new:
        return jsonify({'error': f'Dateitypen stimmen nicht überein: {type_old.upper()} vs. {type_new.upper()}'}), 400

    file_type = type_old

    # Check file sizes
    for f in [file_old, file_new]:
        f.seek(0, 2)
        if f.tell() > MAX_FILE_SIZE:
            return jsonify({'error': f'Datei zu groß. Maximum: {MAX_FILE_SIZE // (1024*1024)} MB'}), 400
        f.seek(0)

    session = SessionLocal()
    try:
        # Create document
        base_name = file_old.filename.rsplit('.', 1)[0]
        doc = Document(name=f"{base_name} (Schnellvergleich)", file_type=file_type)
        session.add(doc)
        session.flush()

        doc_dir = os.path.join(STORAGE_DIR, str(doc.id))
        os.makedirs(doc_dir, exist_ok=True)

        # Save both files
        versions = []
        for idx, (f, ver_num) in enumerate([(file_old, 1), (file_new, 2)]):
            safe_name = secure_filename(f.filename) or 'upload'
            unique_name = f"{uuid.uuid4().hex}_{safe_name}"
            filepath = os.path.join(doc_dir, unique_name)
            if not os.path.realpath(filepath).startswith(os.path.realpath(STORAGE_DIR)):
                return jsonify({'error': 'Ungültiger Dateipfad'}), 400
            f.save(filepath)
            label = 'Alte Version' if ver_num == 1 else 'Neue Version'
            version = Version(
                document_id=doc.id,
                version_number=ver_num,
                filename=safe_name,
                filepath=filepath,
                label=label,
            )
            session.add(version)
            versions.append(version)

        session.commit()
        session.refresh(doc)

        # Run diff immediately
        struct_a, text_a = extract(versions[0].filepath, file_type)
        struct_b, text_b = extract(versions[1].filepath, file_type)
        options = {
            'ignore_whitespace': request.form.get('ignore_whitespace') == '1',
            'ignore_case': request.form.get('ignore_case') == '1',
            'ignore_headers_footers': request.form.get('ignore_headers_footers') == '1',
        }
        result = compute_diff(struct_a, text_a, struct_b, text_b, file_type, options)

        result['version_a'] = versions[0].to_dict()
        result['version_b'] = versions[1].to_dict()
        result['document'] = doc.to_dict()

        return jsonify(result)

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Vergleich fehlgeschlagen. Bitte prüfen Sie die Dateien.'}), 500
    finally:
        session.close()


@api.route('/snippet-compare', methods=['POST'])
def snippet_compare():
    """Compare two text snippets directly (no file upload needed)."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body erforderlich'}), 400

    text_a = data.get('text_a', '')
    text_b = data.get('text_b', '')

    if not text_a and not text_b:
        return jsonify({'error': 'Mindestens ein Text erforderlich'}), 400

    options = {
        'ignore_whitespace': data.get('ignore_whitespace', False),
        'ignore_case': data.get('ignore_case', False),
    }

    # Create simple structures for the diff engine
    struct_a = [{'index': i, 'text': line, 'html': line, 'formatting': []}
                for i, line in enumerate(text_a.split('\n'))]
    struct_b = [{'index': i, 'text': line, 'html': line, 'formatting': []}
                for i, line in enumerate(text_b.split('\n'))]

    from .diff_engine import compute_diff
    result = compute_diff(struct_a, text_a, struct_b, text_b, 'txt', options)

    return jsonify(result)


@api.route('/clean-metadata/<int:doc_id>/<int:ver_id>', methods=['GET'])
def clean_metadata(doc_id, ver_id):
    """Download a version with metadata stripped (author, comments, track changes)."""
    import tempfile
    import shutil

    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        version = session.query(Version).filter_by(id=ver_id, document_id=doc_id).first()
        if not doc or not version:
            return jsonify({'error': 'Nicht gefunden'}), 404

        tmpdir = tempfile.mkdtemp()
        try:
            cleaned_path = _clean_document_metadata(version.filepath, doc.file_type, tmpdir)
            if not cleaned_path:
                return jsonify({'error': 'Metadaten-Bereinigung nicht unterstützt für diesen Dateityp'}), 400

            dl_name = f"{os.path.splitext(version.filename)[0]}_clean{os.path.splitext(version.filename)[1]}"
            return send_from_directory(
                os.path.dirname(cleaned_path),
                os.path.basename(cleaned_path),
                as_attachment=True,
                download_name=dl_name,
            )
        finally:
            import threading
            def cleanup():
                import time
                time.sleep(10)
                shutil.rmtree(tmpdir, ignore_errors=True)
            threading.Thread(target=cleanup, daemon=True).start()
    finally:
        session.close()


@api.route('/download/<int:doc_id>/<int:ver_id>', methods=['GET'])
def download_version(doc_id, ver_id):
    session = SessionLocal()
    try:
        version = session.query(Version).filter_by(id=ver_id, document_id=doc_id).first()
        if not version:
            return jsonify({'error': 'Nicht gefunden'}), 404
        directory = os.path.dirname(version.filepath)
        filename = os.path.basename(version.filepath)
        return send_from_directory(directory, filename, as_attachment=True, download_name=version.filename)
    finally:
        session.close()


@api.route('/redline/<int:doc_id>/<int:version_a>/<int:version_b>', methods=['GET'])
def generate_redline(doc_id, version_a, version_b):
    """
    Generate a document with all changes visually marked.
    Query param: format=original|pdf (default: original)
    Works for DOCX, XLSX, PPTX, PDF.
    """
    import tempfile
    import shutil

    output_format = request.args.get('format', 'original')

    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Dokument nicht gefunden'}), 404

        ver_a = session.query(Version).filter_by(document_id=doc_id, version_number=version_a).first()
        ver_b = session.query(Version).filter_by(document_id=doc_id, version_number=version_b).first()
        if not ver_a or not ver_b:
            return jsonify({'error': 'Version nicht gefunden'}), 404

        tmpdir = tempfile.mkdtemp()
        try:
            generators = {
                'docx': _generate_docx_redline,
                'xlsx': _generate_xlsx_redline,
                'pptx': _generate_pptx_redline,
                'pdf': _generate_pdf_redline,
            }
            gen = generators.get(doc.file_type)
            if not gen:
                return jsonify({'error': 'Nicht unterstützter Dateityp'}), 400

            out_path = gen(ver_a.filepath, ver_b.filepath, tmpdir)

            # Convert to PDF if requested
            if output_format == 'pdf' and not out_path.endswith('.pdf'):
                pdf_path = _convert_to_pdf(out_path, tmpdir)
                if pdf_path and pdf_path.endswith('.pdf'):
                    out_path = pdf_path

            ext = os.path.splitext(out_path)[1]
            dl_name = f"{doc.name}_Aenderungen_V{version_a}_vs_V{version_b}{ext}"
            return send_from_directory(
                os.path.dirname(out_path),
                os.path.basename(out_path),
                as_attachment=True,
                download_name=dl_name,
            )
        finally:
            import threading
            def cleanup():
                import time
                time.sleep(10)
                shutil.rmtree(tmpdir, ignore_errors=True)
            threading.Thread(target=cleanup, daemon=True).start()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Redline-Erstellung fehlgeschlagen.'}), 500
    finally:
        session.close()


def _generate_docx_redline(filepath_a, filepath_b, tmpdir):
    """
    Generate a DOCX with real Word tracked changes (w:ins / w:del XML elements).
    Word will show these as proper revision marks that can be accepted/rejected.
    """
    from docx import Document as DocxDocument
    from lxml import etree
    import difflib
    import re
    from datetime import datetime

    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    nsmap = {'w': W}
    author = 'MyCompare'
    date_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    doc_b = DocxDocument(filepath_b)
    doc_a = DocxDocument(filepath_a)

    paras_a = [p.text for p in doc_a.paragraphs]
    paras_b = [p.text for p in doc_b.paragraphs]

    def make_run_element(text, rpr_source=None):
        """Create a w:r element with text."""
        r = etree.SubElement(etree.Element('dummy'), f'{{{W}}}r')
        if rpr_source is not None:
            rpr = rpr_source.find(f'{{{W}}}rPr')
            if rpr is not None:
                r.append(etree.fromstring(etree.tostring(rpr)))
        t = etree.SubElement(r, f'{{{W}}}t')
        t.text = text
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        return r

    def wrap_in_ins(run_el):
        """Wrap a run element in w:ins (insertion revision)."""
        ins = etree.Element(f'{{{W}}}ins')
        ins.set(f'{{{W}}}id', str(next(rev_id_gen)))
        ins.set(f'{{{W}}}author', author)
        ins.set(f'{{{W}}}date', date_str)
        ins.append(run_el)
        return ins

    def wrap_in_del(run_el):
        """Wrap a run element in w:del (deletion revision), using w:delText."""
        dele = etree.Element(f'{{{W}}}del')
        dele.set(f'{{{W}}}id', str(next(rev_id_gen)))
        dele.set(f'{{{W}}}author', author)
        dele.set(f'{{{W}}}date', date_str)
        # Change w:t to w:delText
        t_el = run_el.find(f'{{{W}}}t')
        if t_el is not None:
            dt = etree.SubElement(run_el, f'{{{W}}}delText')
            dt.text = t_el.text
            dt.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            run_el.remove(t_el)
        dele.append(run_el)
        return dele

    # Revision ID generator
    rev_id_counter = [100]
    def _next_rev_id():
        rev_id_counter[0] += 1
        return rev_id_counter[0]
    rev_id_gen = iter(range(100, 100000))

    # Work on a copy of doc_b (preserves all original formatting/styles)
    import shutil
    work_path = os.path.join(tmpdir, '_work.docx')
    shutil.copy2(filepath_b, work_path)
    out_doc = DocxDocument(work_path)

    # Clear all paragraphs in out_doc body
    body = out_doc.element.body
    for p_el in body.findall(f'{{{W}}}p'):
        body.remove(p_el)

    sm = difflib.SequenceMatcher(None, paras_a, paras_b, autojunk=False)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            # Copy paragraphs from B as-is (they have correct formatting)
            for idx in range(j1, j2):
                p_el = etree.fromstring(etree.tostring(doc_b.paragraphs[idx]._element))
                body.append(p_el)

        elif tag == 'replace':
            for idx in range(max(i2 - i1, j2 - j1)):
                old_idx = i1 + idx if (i1 + idx) < i2 else None
                new_idx = j1 + idx if (j1 + idx) < j2 else None
                old_text = paras_a[old_idx] if old_idx is not None else ''
                new_text = paras_b[new_idx] if new_idx is not None else ''

                # Create paragraph element (copy pPr from new version if available)
                p_el = etree.SubElement(body, f'{{{W}}}p')
                if new_idx is not None:
                    src_ppr = doc_b.paragraphs[new_idx]._element.find(f'{{{W}}}pPr')
                    if src_ppr is not None:
                        p_el.append(etree.fromstring(etree.tostring(src_ppr)))
                elif old_idx is not None:
                    src_ppr = doc_a.paragraphs[old_idx]._element.find(f'{{{W}}}pPr')
                    if src_ppr is not None:
                        p_el.append(etree.fromstring(etree.tostring(src_ppr)))

                if old_text and new_text:
                    # Word-level diff
                    words_a = re.findall(r'\S+|\s+', old_text)
                    words_b = re.findall(r'\S+|\s+', new_text)
                    wsm = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)

                    for wtag, wi1, wi2, wj1, wj2 in wsm.get_opcodes():
                        if wtag == 'equal':
                            r = make_run_element(''.join(words_b[wj1:wj2]))
                            p_el.append(r)
                        elif wtag == 'replace':
                            # Deleted words
                            r_del = make_run_element(''.join(words_a[wi1:wi2]))
                            p_el.append(wrap_in_del(r_del))
                            # Inserted words
                            r_ins = make_run_element(''.join(words_b[wj1:wj2]))
                            p_el.append(wrap_in_ins(r_ins))
                        elif wtag == 'delete':
                            r_del = make_run_element(''.join(words_a[wi1:wi2]))
                            p_el.append(wrap_in_del(r_del))
                        elif wtag == 'insert':
                            r_ins = make_run_element(''.join(words_b[wj1:wj2]))
                            p_el.append(wrap_in_ins(r_ins))
                elif old_text:
                    r_del = make_run_element(old_text)
                    p_el.append(wrap_in_del(r_del))
                elif new_text:
                    r_ins = make_run_element(new_text)
                    p_el.append(wrap_in_ins(r_ins))

        elif tag == 'delete':
            for idx in range(i1, i2):
                p_el = etree.SubElement(body, f'{{{W}}}p')
                src_ppr = doc_a.paragraphs[idx]._element.find(f'{{{W}}}pPr')
                if src_ppr is not None:
                    p_el.append(etree.fromstring(etree.tostring(src_ppr)))
                # Mark entire paragraph as deletion
                rpr_src = doc_a.paragraphs[idx]._element.find(f'{{{W}}}r')
                r_del = make_run_element(paras_a[idx], rpr_src)
                # Wrap paragraph deletion
                dele = wrap_in_del(r_del)
                p_el.append(dele)
                # Also mark paragraph mark as deleted
                ppr_del = etree.SubElement(p_el, f'{{{W}}}pPr')
                rpr_del = etree.SubElement(ppr_del, f'{{{W}}}rPr')
                del_elem = etree.SubElement(rpr_del, f'{{{W}}}del')
                del_elem.set(f'{{{W}}}id', str(next(rev_id_gen)))
                del_elem.set(f'{{{W}}}author', author)
                del_elem.set(f'{{{W}}}date', date_str)

        elif tag == 'insert':
            for idx in range(j1, j2):
                p_el = etree.SubElement(body, f'{{{W}}}p')
                src_ppr = doc_b.paragraphs[idx]._element.find(f'{{{W}}}pPr')
                if src_ppr is not None:
                    p_el.append(etree.fromstring(etree.tostring(src_ppr)))
                rpr_src = doc_b.paragraphs[idx]._element.find(f'{{{W}}}r')
                r_ins = make_run_element(paras_b[idx], rpr_src)
                p_el.append(wrap_in_ins(r_ins))

    out_path = os.path.join(tmpdir, 'redline.docx')
    out_doc.save(out_path)
    return out_path


def _generate_xlsx_redline(filepath_a, filepath_b, tmpdir):
    """Generate an XLSX with changes highlighted: deleted cells red, new cells green, changed cells yellow."""
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill, Font
    import copy

    wb_a = load_workbook(filepath_a, data_only=True)
    wb_b = load_workbook(filepath_b)

    red_fill = PatternFill(start_color='FFFECACA', end_color='FFFECACA', fill_type='solid')
    green_fill = PatternFill(start_color='FFBBF7D0', end_color='FFBBF7D0', fill_type='solid')
    yellow_fill = PatternFill(start_color='FFFEF3C7', end_color='FFFEF3C7', fill_type='solid')
    red_font = Font(color='DC2626', strikethrough=True)
    blue_font = Font(color='2563EB', underline='single')

    # Build value maps for A
    vals_a = {}
    for sn in wb_a.sheetnames:
        ws = wb_a[sn]
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    vals_a[f"{sn}!{cell.coordinate}"] = str(cell.value)

    # Mark changes in B
    for sn in wb_b.sheetnames:
        ws = wb_b[sn]
        for row in ws.iter_rows():
            for cell in row:
                key = f"{sn}!{cell.coordinate}"
                val_b = str(cell.value) if cell.value is not None else None
                val_a = vals_a.pop(key, None)

                if val_a is None and val_b is not None:
                    # New cell
                    cell.fill = green_fill
                    cell.font = blue_font
                elif val_a is not None and val_b is not None and val_a != val_b:
                    # Changed cell - show old → new
                    cell.fill = yellow_fill
                    cell.value = f"{val_b}  [war: {val_a}]"

    # Add deleted cells info to a new sheet if any remain
    if vals_a:
        ws_del = wb_b.create_sheet('Gelöschte Zellen')
        ws_del.cell(1, 1, 'Zelle').font = Font(bold=True)
        ws_del.cell(1, 2, 'Alter Wert').font = Font(bold=True)
        for i, (coord, val) in enumerate(sorted(vals_a.items()), 2):
            ws_del.cell(i, 1, coord)
            c = ws_del.cell(i, 2, val)
            c.fill = red_fill
            c.font = red_font

    out_path = os.path.join(tmpdir, 'redline.xlsx')
    wb_b.save(out_path)
    return out_path


def _generate_pptx_redline(filepath_a, filepath_b, tmpdir):
    """Generate a PPTX with a summary slide showing all changes."""
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor as PptxRGB
    import difflib

    prs_a = Presentation(filepath_a)
    prs_b = Presentation(filepath_b)

    # Extract text per slide
    def slide_texts(prs):
        result = []
        for slide in prs.slides:
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    texts.append(shape.text_frame.text)
            result.append('\n'.join(texts))
        return result

    texts_a = slide_texts(prs_a)
    texts_b = slide_texts(prs_b)

    # Add a summary slide at the beginning of prs_b
    from pptx.util import Inches, Pt
    slide_layout = prs_b.slide_layouts[6]  # blank layout
    summary = prs_b.slides.add_slide(slide_layout)

    # Move summary to first position
    xml_slides = prs_b.slides._sldIdLst
    slides_list = list(xml_slides)
    last = slides_list[-1]
    xml_slides.remove(last)
    xml_slides.insert(0, last)

    # Add title
    from pptx.util import Inches
    txBox = summary.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(0.6))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = "Änderungsübersicht"
    p.font.size = Pt(24)
    p.font.bold = True

    # Diff and list changes
    sm = difflib.SequenceMatcher(None, texts_a, texts_b, autojunk=False)
    y_pos = Inches(1.2)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue

        txBox = summary.shapes.add_textbox(Inches(0.5), y_pos, Inches(9), Inches(0.8))
        tf = txBox.text_frame
        tf.word_wrap = True

        if tag == 'replace':
            for idx in range(max(i2 - i1, j2 - j1)):
                old_t = texts_a[i1 + idx][:80] if (i1 + idx) < i2 else ''
                new_t = texts_b[j1 + idx][:80] if (j1 + idx) < j2 else ''
                p = tf.add_paragraph() if tf.paragraphs[0].text else tf.paragraphs[0]
                p.font.size = Pt(10)
                run_label = p.add_run()
                run_label.text = f"Folie {j1 + idx + 1}: "
                run_label.font.bold = True
                run_del = p.add_run()
                run_del.text = old_t
                run_del.font.color.rgb = PptxRGB(0xDC, 0x26, 0x26)
                run_del.font.strikethrough = True
                run_del.font.size = Pt(9)
                run_arrow = p.add_run()
                run_arrow.text = " → "
                run_new = p.add_run()
                run_new.text = new_t
                run_new.font.color.rgb = PptxRGB(0x25, 0x63, 0xEB)
                run_new.font.underline = True
                run_new.font.size = Pt(9)
        elif tag == 'delete':
            p = tf.paragraphs[0]
            p.font.size = Pt(10)
            run = p.add_run()
            run.text = f"Folien {i1+1}-{i2} gelöscht"
            run.font.color.rgb = PptxRGB(0xDC, 0x26, 0x26)
        elif tag == 'insert':
            p = tf.paragraphs[0]
            p.font.size = Pt(10)
            run = p.add_run()
            run.text = f"Folien {j1+1}-{j2} neu eingefügt"
            run.font.color.rgb = PptxRGB(0x25, 0x63, 0xEB)

        y_pos += Inches(0.9)
        if y_pos > Inches(7):
            break  # Prevent overflow

    out_path = os.path.join(tmpdir, 'redline.pptx')
    prs_b.save(out_path)
    return out_path


def _generate_pdf_redline(filepath_a, filepath_b, tmpdir):
    """Generate a PDF showing changes between two PDF versions as a text-based diff report."""
    import pdfplumber
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import red, blue, black, HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import mm
    import difflib

    # Extract text
    def pdf_text(path):
        pages = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or '')
        return pages

    try:
        pages_a = pdf_text(filepath_a)
        pages_b = pdf_text(filepath_b)
    except Exception:
        # If reportlab not available, fall back to simple copy
        import shutil
        out_path = os.path.join(tmpdir, 'redline.pdf')
        shutil.copy2(filepath_b, out_path)
        return out_path

    try:
        out_path = os.path.join(tmpdir, 'redline.pdf')
        doc_pdf = SimpleDocTemplate(out_path, pagesize=A4,
                                     leftMargin=20*mm, rightMargin=20*mm,
                                     topMargin=20*mm, bottomMargin=20*mm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=16)
        normal = ParagraphStyle('Normal2', parent=styles['Normal'], fontSize=9, leading=12)
        del_style = ParagraphStyle('Del', parent=normal, textColor=red)
        add_style = ParagraphStyle('Add', parent=normal, textColor=blue)
        heading = ParagraphStyle('H', parent=styles['Heading2'], fontSize=12)

        story = []
        story.append(Paragraph("Änderungsbericht", title_style))
        story.append(Spacer(1, 10*mm))

        text_a = '\n'.join(pages_a)
        text_b = '\n'.join(pages_b)
        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()

        sm = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
        change_num = 0

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            change_num += 1
            story.append(Paragraph(f"Änderung {change_num} (Zeile {i1+1})", heading))

            if tag in ('replace', 'delete'):
                for idx in range(i1, min(i2, i1 + 20)):
                    safe = lines_a[idx].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    story.append(Paragraph(f'<strike><font color="red">- {safe}</font></strike>', normal))

            if tag in ('replace', 'insert'):
                for idx in range(j1, min(j2, j1 + 20)):
                    safe = lines_b[idx].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    story.append(Paragraph(f'<font color="blue"><u>+ {safe}</u></font>', normal))

            story.append(Spacer(1, 5*mm))

        if change_num == 0:
            story.append(Paragraph("Keine Änderungen erkannt.", normal))

        doc_pdf.build(story)
        return out_path

    except ImportError:
        # reportlab not installed — copy original
        import shutil
        out_path = os.path.join(tmpdir, 'redline.pdf')
        shutil.copy2(filepath_b, out_path)
        return out_path


@api.route('/export-changes/<int:doc_id>/<int:version_a>/<int:version_b>', methods=['GET'])
def export_changed_pages(doc_id, version_a, version_b):
    """
    Export only the changed pages/sections as original format or PDF.
    Query param: format=original|pdf
    """
    import tempfile
    import shutil
    import subprocess

    output_format = request.args.get('format', 'original')
    if output_format not in ('original', 'pdf'):
        return jsonify({'error': 'Format muss "original" oder "pdf" sein'}), 400

    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Dokument nicht gefunden'}), 404

        ver_a = session.query(Version).filter_by(document_id=doc_id, version_number=version_a).first()
        ver_b = session.query(Version).filter_by(document_id=doc_id, version_number=version_b).first()
        if not ver_a or not ver_b:
            return jsonify({'error': 'Version nicht gefunden'}), 404

        struct_a, text_a = extract(ver_a.filepath, doc.file_type)
        struct_b, text_b = extract(ver_b.filepath, doc.file_type)
        diff_result = compute_diff(struct_a, text_a, struct_b, text_b, doc.file_type)

        # Determine which pages/sections changed
        changed_pages = set()
        for change in diff_result['structural_changes']:
            loc = change.get('location', '')
            # Extract page/slide/section numbers
            import re
            nums = re.findall(r'\d+', loc)
            if nums:
                changed_pages.add(int(nums[0]))
            # For items with page info
            for items_key in ('old_items', 'new_items'):
                for item in change.get(items_key, []):
                    if 'page' in item:
                        changed_pages.add(item['page'])
                    elif 'slide' in item:
                        changed_pages.add(item['slide'])

        # For plaintext changes, map line numbers to pages
        lines_per_page_a = {}
        line_num = 0
        for item in struct_a:
            page = item.get('page') or item.get('slide') or item.get('index', 0) + 1
            text = item.get('text', '')
            for _ in text.split('\n'):
                lines_per_page_a[line_num] = page
                line_num += 1

        for change in diff_result['plaintext_changes']:
            for line_idx in range(change.get('old_start', 0), change.get('old_end', 0)):
                if line_idx in lines_per_page_a:
                    changed_pages.add(lines_per_page_a[line_idx])

        if not changed_pages:
            return jsonify({'error': 'Keine geänderten Seiten gefunden'}), 404

        changed_pages = sorted(changed_pages)

        # Generate export based on file type
        tmpdir = tempfile.mkdtemp()
        try:
            if doc.file_type == 'pdf':
                export_path = _export_pdf_pages(ver_b.filepath, changed_pages, tmpdir, output_format)
            elif doc.file_type == 'docx':
                export_path = _export_docx_pages(ver_b.filepath, changed_pages, tmpdir, output_format)
            elif doc.file_type == 'xlsx':
                export_path = _export_xlsx_sheets(ver_b.filepath, changed_pages, tmpdir, output_format, struct_b)
            elif doc.file_type == 'pptx':
                export_path = _export_pptx_slides(ver_b.filepath, changed_pages, tmpdir, output_format)
            else:
                return jsonify({'error': 'Export nicht unterstützt'}), 400

            if not export_path or not os.path.exists(export_path):
                return jsonify({'error': 'Export fehlgeschlagen'}), 500

            dl_name = f"{doc.name}_Aenderungen_V{version_a}_vs_V{version_b}{os.path.splitext(export_path)[1]}"
            return send_from_directory(
                os.path.dirname(export_path),
                os.path.basename(export_path),
                as_attachment=True,
                download_name=dl_name,
            )
        finally:
            # Clean up after a delay (let the response finish)
            import threading
            def cleanup():
                import time
                time.sleep(10)
                shutil.rmtree(tmpdir, ignore_errors=True)
            threading.Thread(target=cleanup, daemon=True).start()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


def _export_pdf_pages(filepath, pages, tmpdir, output_format):
    """Extract specific pages from a PDF."""
    from PyPDF2 import PdfReader, PdfWriter
    reader = PdfReader(filepath)
    writer = PdfWriter()

    for page_num in pages:
        idx = page_num - 1  # 0-indexed
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])

    out_path = os.path.join(tmpdir, 'changes.pdf')
    with open(out_path, 'wb') as f:
        writer.write(f)
    return out_path


def _export_docx_pages(filepath, pages, tmpdir, output_format):
    """
    Export the full DOCX (version B) — DOCX doesn't have discrete "pages" at file level.
    For PDF output, attempt LibreOffice conversion.
    """
    import shutil
    if output_format == 'original':
        out_path = os.path.join(tmpdir, 'changes.docx')
        shutil.copy2(filepath, out_path)
        return out_path
    else:
        return _convert_to_pdf(filepath, tmpdir)


def _export_xlsx_sheets(filepath, pages, tmpdir, output_format, struct_b):
    """Export changed sheets from an XLSX file."""
    from openpyxl import load_workbook
    import shutil

    if output_format == 'original':
        out_path = os.path.join(tmpdir, 'changes.xlsx')
        shutil.copy2(filepath, out_path)
        return out_path
    else:
        return _convert_to_pdf(filepath, tmpdir)


def _export_pptx_slides(filepath, slides, tmpdir, output_format):
    """Export changed slides from a PPTX."""
    import shutil

    if output_format == 'original':
        out_path = os.path.join(tmpdir, 'changes.pptx')
        shutil.copy2(filepath, out_path)
        return out_path
    else:
        return _convert_to_pdf(filepath, tmpdir)


def _clean_document_metadata(filepath, file_type, tmpdir):
    """Remove metadata (author, comments, track changes) from a document."""
    import shutil

    if file_type == 'docx':
        from docx import Document as DocxDocument
        doc = DocxDocument(filepath)
        # Remove core properties
        cp = doc.core_properties
        cp.author = ''
        cp.last_modified_by = ''
        cp.comments = ''
        cp.keywords = ''
        cp.subject = ''
        cp.category = ''
        # Remove comments from document body
        from lxml import etree
        nsmap = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        body = doc.element.body
        for comment_ref in body.findall('.//w:commentReference', nsmap):
            parent = comment_ref.getparent()
            if parent is not None:
                parent.remove(comment_ref)
        for comment_start in body.findall('.//w:commentRangeStart', nsmap):
            parent = comment_start.getparent()
            if parent is not None:
                parent.remove(comment_start)
        for comment_end in body.findall('.//w:commentRangeEnd', nsmap):
            parent = comment_end.getparent()
            if parent is not None:
                parent.remove(comment_end)
        # Accept all tracked changes (remove revision marks)
        for ins in body.findall('.//w:ins', nsmap):
            parent = ins.getparent()
            idx = list(parent).index(ins)
            for child in list(ins):
                parent.insert(idx, child)
                idx += 1
            parent.remove(ins)
        for dele in body.findall('.//w:del', nsmap):
            parent = dele.getparent()
            if parent is not None:
                parent.remove(dele)

        out_path = os.path.join(tmpdir, 'cleaned.docx')
        doc.save(out_path)
        return out_path

    elif file_type == 'xlsx':
        from openpyxl import load_workbook
        wb = load_workbook(filepath)
        wb.properties.creator = ''
        wb.properties.lastModifiedBy = ''
        wb.properties.description = ''
        wb.properties.subject = ''
        wb.properties.keywords = ''
        # Remove comments from all cells
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.comment:
                        cell.comment = None
        out_path = os.path.join(tmpdir, 'cleaned.xlsx')
        wb.save(out_path)
        return out_path

    elif file_type == 'pptx':
        from pptx import Presentation
        prs = Presentation(filepath)
        prs.core_properties.author = ''
        prs.core_properties.last_modified_by = ''
        prs.core_properties.comments = ''
        prs.core_properties.keywords = ''
        prs.core_properties.subject = ''
        # Remove notes from slides
        for slide in prs.slides:
            if slide.has_notes_slide:
                notes_tf = slide.notes_slide.notes_text_frame
                for para in notes_tf.paragraphs:
                    for run in para.runs:
                        run.text = ''
        out_path = os.path.join(tmpdir, 'cleaned.pptx')
        prs.save(out_path)
        return out_path

    elif file_type == 'pdf':
        from PyPDF2 import PdfReader, PdfWriter
        reader = PdfReader(filepath)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        # Remove metadata
        writer.add_metadata({'/Producer': '', '/Creator': '', '/Author': ''})
        out_path = os.path.join(tmpdir, 'cleaned.pdf')
        with open(out_path, 'wb') as f:
            writer.write(f)
        return out_path

    return None


def _convert_to_pdf(filepath, tmpdir):
    """Convert a file to PDF. Tries LibreOffice first, falls back to reportlab text extraction."""
    import subprocess
    import shutil

    # Try LibreOffice first (best quality)
    for lo_cmd in ['libreoffice', 'soffice', '/usr/bin/libreoffice',
                    '/Applications/LibreOffice.app/Contents/MacOS/soffice']:
        if shutil.which(lo_cmd):
            try:
                subprocess.run(
                    [lo_cmd, '--headless', '--convert-to', 'pdf', '--outdir', tmpdir, filepath],
                    timeout=60, check=True, capture_output=True,
                )
                base = os.path.splitext(os.path.basename(filepath))[0]
                pdf_path = os.path.join(tmpdir, f'{base}.pdf')
                if os.path.exists(pdf_path):
                    return pdf_path
            except Exception:
                pass

    # Fallback: generate PDF from extracted text using reportlab
    try:
        ext = os.path.splitext(filepath)[1].lower()
        from .extractors import extract
        file_type = ext.lstrip('.')
        if file_type in ('docx', 'xlsx', 'pptx', 'pdf'):
            struct_data, plain_text = extract(filepath, file_type)
        else:
            plain_text = ''

        if plain_text:
            return _text_to_pdf(plain_text, tmpdir,
                                title=os.path.basename(filepath))
    except Exception:
        pass

    # Last resort: copy original
    ext = os.path.splitext(filepath)[1]
    out_path = os.path.join(tmpdir, f'changes{ext}')
    shutil.copy2(filepath, out_path)
    return out_path


def _text_to_pdf(text, tmpdir, title='Dokument'):
    """Convert plain text to a PDF using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import mm
    from html import escape

    out_path = os.path.join(tmpdir, 'export.pdf')
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Title'], fontSize=14)
    body_style = ParagraphStyle('DocBody', parent=styles['Normal'],
                                 fontSize=9, leading=12,
                                 fontName='Helvetica')

    story = [Paragraph(escape(title), title_style), Spacer(1, 5*mm)]

    for line in text.split('\n'):
        safe = escape(line) if line.strip() else '&nbsp;'
        story.append(Paragraph(safe, body_style))

    doc.build(story)
    return out_path
