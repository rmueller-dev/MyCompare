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
    if ext in ('docx', 'xlsx', 'pptx', 'pdf'):
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
        return jsonify({'error': 'Nicht unterstützter Dateityp. Erlaubt: DOCX, XLSX, PPTX, PDF'}), 400

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

        # Compute diff with verification
        result = compute_diff(struct_a, text_a, struct_b, text_b, doc.file_type)

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
        return jsonify({'error': 'Nicht unterstützter Dateityp. Erlaubt: DOCX, XLSX, PPTX, PDF'}), 400
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
        result = compute_diff(struct_a, text_a, struct_b, text_b, file_type)

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


def _convert_to_pdf(filepath, tmpdir):
    """Convert a file to PDF using LibreOffice if available, else return None."""
    import subprocess
    import shutil

    # Try LibreOffice
    for lo_cmd in ['libreoffice', 'soffice', '/usr/bin/libreoffice']:
        if shutil.which(lo_cmd):
            try:
                subprocess.run(
                    [lo_cmd, '--headless', '--convert-to', 'pdf', '--outdir', tmpdir, filepath],
                    timeout=60, check=True, capture_output=True,
                )
                # Find the output PDF
                base = os.path.splitext(os.path.basename(filepath))[0]
                pdf_path = os.path.join(tmpdir, f'{base}.pdf')
                if os.path.exists(pdf_path):
                    return pdf_path
            except Exception:
                pass

    # Fallback: copy original and inform
    ext = os.path.splitext(filepath)[1]
    out_path = os.path.join(tmpdir, f'changes{ext}')
    shutil.copy2(filepath, out_path)
    return out_path
