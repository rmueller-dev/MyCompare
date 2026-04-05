"""Flask API routes."""
import os
import uuid
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from .models import SessionLocal, Document, Version, RenderingSet, Folder, STORAGE_DIR
from .extractors import extract
from .diff_engine import compute_diff
from .image_diff import extract_images, compare_images
from .ai_analysis import analyze_changes, _check_ollama, get_providers_status, set_api_key, get_api_key

api = Blueprint('api', __name__, url_prefix='/api')

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def get_file_type(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext in ('docx', 'xlsx', 'pptx', 'pdf', 'rtf', 'txt', 'html', 'htm'):
        return ext
    return None


@api.route('/documents', methods=['GET'])
def list_documents():
    session = SessionLocal()
    try:
        show_archived = request.args.get('archived', 'false') == 'true'
        q = session.query(Document)
        if not show_archived:
            q = q.filter((Document.archived == False) | (Document.archived == None))  # noqa: E712
        docs = q.order_by(Document.created_at.desc()).all()
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
        return jsonify({'error': 'Nicht unterstützter Dateityp. Erlaubt: DOCX, XLSX, PPTX, PDF, RTF, TXT, HTML'}), 400

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


# ─── FOLDERS ────────────────────────────────────────────────────────────

@api.route('/folders', methods=['GET'])
def list_folders():
    session = SessionLocal()
    try:
        show_archived = request.args.get('archived', 'false') == 'true'
        q = session.query(Folder)
        if not show_archived:
            q = q.filter((Folder.archived == False) | (Folder.archived == None))  # noqa: E712
        folders = q.order_by(Folder.name).all()
        return jsonify([f.to_dict() for f in folders])
    finally:
        session.close()


@api.route('/folders', methods=['POST'])
def create_folder():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Ordnername fehlt'}), 400
    parent_id = data.get('parent_id')
    session = SessionLocal()
    try:
        folder = Folder(name=name, parent_id=parent_id)
        session.add(folder)
        session.commit()
        session.refresh(folder)
        return jsonify(folder.to_dict()), 201
    finally:
        session.close()


@api.route('/folders/<int:folder_id>', methods=['PUT'])
def update_folder(folder_id):
    data = request.get_json() or {}
    session = SessionLocal()
    try:
        folder = session.query(Folder).get(folder_id)
        if not folder:
            return jsonify({'error': 'Ordner nicht gefunden'}), 404
        if 'name' in data:
            folder.name = data['name'].strip()
        if 'parent_id' in data:
            folder.parent_id = data['parent_id']
        session.commit()
        session.refresh(folder)
        return jsonify(folder.to_dict())
    finally:
        session.close()


@api.route('/folders/<int:folder_id>', methods=['DELETE'])
def delete_folder(folder_id):
    session = SessionLocal()
    try:
        folder = session.query(Folder).get(folder_id)
        if not folder:
            return jsonify({'error': 'Ordner nicht gefunden'}), 404
        # Move documents in this folder to root (no folder)
        for doc in folder.documents:
            doc.folder_id = None
        # Move child folders to parent
        children = session.query(Folder).filter_by(parent_id=folder_id).all()
        for child in children:
            child.parent_id = folder.parent_id
        session.delete(folder)
        session.commit()
        return jsonify({'ok': True})
    finally:
        session.close()


# ─── ARCHIVE / MOVE / SEARCH ───────────────────────────────────────────

@api.route('/documents/<int:doc_id>/archive', methods=['POST'])
def archive_document(doc_id):
    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Nicht gefunden'}), 404
        doc.archived = True
        session.commit()
        return jsonify({'ok': True, 'archived': True})
    finally:
        session.close()


@api.route('/documents/<int:doc_id>/unarchive', methods=['POST'])
def unarchive_document(doc_id):
    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Nicht gefunden'}), 404
        doc.archived = False
        session.commit()
        return jsonify({'ok': True, 'archived': False})
    finally:
        session.close()


@api.route('/documents/<int:doc_id>/move', methods=['POST'])
def move_document(doc_id):
    data = request.get_json() or {}
    folder_id = data.get('folder_id')  # None = move to root
    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Nicht gefunden'}), 404
        if folder_id is not None:
            folder = session.query(Folder).get(folder_id)
            if not folder:
                return jsonify({'error': 'Ordner nicht gefunden'}), 404
        doc.folder_id = folder_id
        session.commit()
        return jsonify({'ok': True, 'folder_id': folder_id})
    finally:
        session.close()


@api.route('/folders/<int:folder_id>/archive', methods=['POST'])
def archive_folder(folder_id):
    session = SessionLocal()
    try:
        folder = session.query(Folder).get(folder_id)
        if not folder:
            return jsonify({'error': 'Ordner nicht gefunden'}), 404
        folder.archived = True
        # Also archive all documents in this folder
        for doc in folder.documents:
            doc.archived = True
        session.commit()
        return jsonify({'ok': True})
    finally:
        session.close()


@api.route('/folders/<int:folder_id>/unarchive', methods=['POST'])
def unarchive_folder(folder_id):
    session = SessionLocal()
    try:
        folder = session.query(Folder).get(folder_id)
        if not folder:
            return jsonify({'error': 'Ordner nicht gefunden'}), 404
        folder.archived = False
        for doc in folder.documents:
            doc.archived = False
        session.commit()
        return jsonify({'ok': True})
    finally:
        session.close()


@api.route('/search', methods=['GET'])
def search_documents():
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])
    session = SessionLocal()
    try:
        docs = session.query(Document).filter(
            Document.name.ilike(f'%{query}%'),
            (Document.archived == False) | (Document.archived == None),  # noqa: E712
        ).order_by(Document.created_at.desc()).limit(20).all()
        return jsonify([d.to_dict() for d in docs])
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

        # Add pixel-level image comparison for DOCX/PPTX
        if doc.file_type in ('docx', 'pptx'):
            try:
                imgs_a = extract_images(ver_a.filepath, doc.file_type)
                imgs_b = extract_images(ver_b.filepath, doc.file_type)
                image_changes = compare_images(imgs_a, imgs_b)
                # Filter out unchanged images to reduce payload
                result['image_changes'] = [
                    ic for ic in image_changes if ic['type'] != 'unchanged'
                ]
                result['image_summary'] = {
                    'total': len(image_changes),
                    'added': sum(1 for ic in image_changes if ic['type'] == 'added'),
                    'removed': sum(1 for ic in image_changes if ic['type'] == 'removed'),
                    'changed': sum(1 for ic in image_changes if ic['type'] == 'changed'),
                    'unchanged': sum(1 for ic in image_changes if ic['type'] == 'unchanged'),
                }
            except Exception:
                result['image_changes'] = []
                result['image_summary'] = None

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
        return jsonify({'error': 'Nicht unterstützter Dateityp. Erlaubt: DOCX, XLSX, PPTX, PDF, RTF, TXT, HTML'}), 400

    # Cross-format comparison: allow different file types by comparing as plaintext
    cross_format = (type_old != type_new)
    file_type = type_old if not cross_format else 'txt'

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
        # For cross-format: extract each file with its own type, then compare as plaintext
        if cross_format:
            struct_a, text_a = extract(versions[0].filepath, type_old)
            struct_b, text_b = extract(versions[1].filepath, type_new)
            # Normalize to simple text structures for cross-format diff
            struct_a = [{'index': i, 'text': line, 'html': line, 'formatting': []}
                        for i, line in enumerate(text_a.split('\n')) if line.strip()]
            struct_b = [{'index': i, 'text': line, 'html': line, 'formatting': []}
                        for i, line in enumerate(text_b.split('\n')) if line.strip()]
            text_a = '\n'.join(s['text'] for s in struct_a)
            text_b = '\n'.join(s['text'] for s in struct_b)
        else:
            struct_a, text_a = extract(versions[0].filepath, file_type)
            struct_b, text_b = extract(versions[1].filepath, file_type)
        options = {
            'ignore_whitespace': request.form.get('ignore_whitespace') == '1',
            'ignore_case': request.form.get('ignore_case') == '1',
            'ignore_headers_footers': request.form.get('ignore_headers_footers') == '1',
        }
        result = compute_diff(struct_a, text_a, struct_b, text_b, file_type, options)

        # Add pixel-level image comparison for DOCX/PPTX
        if file_type in ('docx', 'pptx'):
            try:
                imgs_a = extract_images(versions[0].filepath, file_type)
                imgs_b = extract_images(versions[1].filepath, file_type)
                image_changes = compare_images(imgs_a, imgs_b)
                result['image_changes'] = [
                    ic for ic in image_changes if ic['type'] != 'unchanged'
                ]
                result['image_summary'] = {
                    'total': len(image_changes),
                    'added': sum(1 for ic in image_changes if ic['type'] == 'added'),
                    'removed': sum(1 for ic in image_changes if ic['type'] == 'removed'),
                    'changed': sum(1 for ic in image_changes if ic['type'] == 'changed'),
                    'unchanged': sum(1 for ic in image_changes if ic['type'] == 'unchanged'),
                }
            except Exception:
                result['image_changes'] = []
                result['image_summary'] = None

        result['version_a'] = versions[0].to_dict()
        result['version_b'] = versions[1].to_dict()
        result['document'] = doc.to_dict()
        if cross_format:
            result['cross_format'] = True
            result['format_a'] = type_old.upper()
            result['format_b'] = type_new.upper()

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


@api.route('/change-report/<int:doc_id>/<int:version_a>/<int:version_b>', methods=['GET'])
def change_report(doc_id, version_a, version_b):
    """Generate a separate DOCX change report with statistics and colored change list."""
    import tempfile
    import shutil

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
            out_path = _generate_docx_report(ver_a.filepath, ver_b.filepath, tmpdir)
            dl_name = f"{doc.name}_Aenderungsbericht_V{version_a}_vs_V{version_b}.docx"
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
        return jsonify({'error': 'Berichterstellung fehlgeschlagen.'}), 500
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

            # If PDF or PDF/A format requested, generate PDF redline directly
            if output_format in ('pdf', 'pdfa') and doc.file_type != 'pdf':
                out_path = _generate_redline_pdf(
                    ver_a.filepath, ver_b.filepath, doc.file_type, tmpdir,
                    pdfa=output_format == 'pdfa')
            elif output_format == 'pdfa' and doc.file_type == 'pdf':
                out_path = _generate_redline_pdf(
                    ver_a.filepath, ver_b.filepath, doc.file_type, tmpdir,
                    pdfa=True)
            else:
                out_path = gen(ver_a.filepath, ver_b.filepath, tmpdir)

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
    Generate a DOCX with real Word tracked changes (w:ins / w:del XML elements)
    following Litera Compare conventions:
    - Summary/change report page at the beginning
    - Legend explaining revision markup
    - Numbered changes with Word comments for navigation
    - Move detection for relocated text
    - Full run formatting preservation from source documents
    Word will show these as proper revision marks that can be accepted/rejected.
    """
    from docx import Document as DocxDocument
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from lxml import etree
    import difflib
    import re
    from datetime import datetime
    from collections import Counter

    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    nsmap = {'w': W}
    author = 'MyCompare'
    date_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    doc_b = DocxDocument(filepath_b)
    doc_a = DocxDocument(filepath_a)

    paras_a = [p.text or '' for p in doc_a.paragraphs]
    paras_b = [p.text or '' for p in doc_b.paragraphs]

    # ── Collect all runs with their formatting from source paragraphs ──
    def get_runs_with_format(para):
        """Extract (text, rPr_xml) tuples from a paragraph's runs."""
        runs = []
        for r_el in para._element.findall(f'{{{W}}}r'):
            t_el = r_el.find(f'{{{W}}}t')
            text = t_el.text if t_el is not None else ''
            rpr = r_el.find(f'{{{W}}}rPr')
            rpr_xml = etree.tostring(rpr) if rpr is not None else None
            runs.append((text or '', rpr_xml))
        return runs

    def make_run_element(text, rpr_xml=None):
        """Create a w:r element with text and optional formatting."""
        r = etree.SubElement(etree.Element('dummy'), f'{{{W}}}r')
        if rpr_xml is not None:
            try:
                r.append(etree.fromstring(rpr_xml))
            except Exception:
                pass
        t = etree.SubElement(r, f'{{{W}}}t')
        t.text = text
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        return r

    def make_run_from_source(run_element):
        """Deep-copy a run element from a source document."""
        return etree.fromstring(etree.tostring(run_element))

    # Revision ID generator
    rev_id_gen = iter(range(500000, 900000))

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
        t_el = run_el.find(f'{{{W}}}t')
        if t_el is not None:
            dt = etree.SubElement(run_el, f'{{{W}}}delText')
            dt.text = t_el.text
            dt.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            run_el.remove(t_el)
        dele.append(run_el)
        return dele

    bookmark_id_gen = iter(range(900000, 999999))

    def add_bookmark(p_el, change_num):
        """Add a w:bookmarkStart / w:bookmarkEnd pair to mark a change for cross-referencing."""
        bm_id = str(next(bookmark_id_gen))
        bm_name = f'_MyCompare_Change_{change_num}'
        # bookmarkStart must come before content, bookmarkEnd after
        bm_start = etree.Element(f'{{{W}}}bookmarkStart')
        bm_start.set(f'{{{W}}}id', bm_id)
        bm_start.set(f'{{{W}}}name', bm_name)
        bm_end = etree.Element(f'{{{W}}}bookmarkEnd')
        bm_end.set(f'{{{W}}}id', bm_id)
        # Insert bookmarkStart after pPr (if present), before runs
        ppr = p_el.find(f'{{{W}}}pPr')
        if ppr is not None:
            ppr.addnext(bm_start)
        else:
            p_el.insert(0, bm_start)
        p_el.append(bm_end)

    # ── Move detection ──
    # Find paragraphs that were deleted in A and inserted in B (same text = move)
    deleted_paras = {}  # text -> list of indices in A
    inserted_paras = {}  # text -> list of indices in B
    sm_pre = difflib.SequenceMatcher(None, paras_a, paras_b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm_pre.get_opcodes():
        if tag == 'delete':
            for idx in range(i1, i2):
                txt = paras_a[idx].strip()
                if txt and len(txt) > 10:
                    deleted_paras.setdefault(txt, []).append(idx)
        elif tag == 'insert':
            for idx in range(j1, j2):
                txt = paras_b[idx].strip()
                if txt and len(txt) > 10:
                    inserted_paras.setdefault(txt, []).append(idx)

    moved_from_a = set()  # indices in A that are "moved from"
    moved_to_b = set()    # indices in B that are "moved to"
    move_pairs = {}       # b_idx -> a_idx
    for txt in deleted_paras:
        if txt in inserted_paras:
            for a_idx, b_idx in zip(deleted_paras[txt], inserted_paras[txt]):
                moved_from_a.add(a_idx)
                moved_to_b.add(b_idx)
                move_pairs[b_idx] = a_idx

    # ── Track changes for summary ──
    all_changes = []  # list of dicts: {type, para_num, old_text, new_text}
    change_counter = [0]

    def record_change(change_type, old_text='', new_text='', para_num=0):
        change_counter[0] += 1
        all_changes.append({
            'num': change_counter[0],
            'type': change_type,
            'old': (old_text or '')[:120],
            'new': (new_text or '')[:120],
            'para': para_num,
        })
        return change_counter[0]

    # ── Merge comments from doc_a into doc_b ──
    # So deleted paragraphs' comments are preserved in the redline
    def _merge_comments_from_a():
        """Copy comments from doc_a into doc_b's comment part, remapping IDs."""
        try:
            comment_part_a = None
            for rel in doc_a.element.part.rels.values():
                if 'comments' in rel.reltype:
                    comment_part_a = rel.target_part
                    break
            if comment_part_a is None:
                return {}

            comment_part_b = None
            for rel in doc_b.element.part.rels.values():
                if 'comments' in rel.reltype:
                    comment_part_b = rel.target_part
                    break

            root_a = etree.fromstring(comment_part_a.blob)
            comments_a = root_a.findall(f'{{{W}}}comment')
            if not comments_a:
                return {}

            # Find max comment ID in B
            max_id = 0
            if comment_part_b is not None:
                root_b = etree.fromstring(comment_part_b.blob)
                for c in root_b.findall(f'{{{W}}}comment'):
                    cid = int(c.get(f'{{{W}}}id', '0'))
                    max_id = max(max_id, cid)

            # Remap and copy comments from A
            id_remap = {}
            if comment_part_b is not None:
                root_b = etree.fromstring(comment_part_b.blob)
            else:
                root_b = etree.Element(f'{{{W}}}comments')

            for c in comments_a:
                old_id = c.get(f'{{{W}}}id', '')
                max_id += 1
                new_id = str(max_id)
                id_remap[old_id] = new_id
                c.set(f'{{{W}}}id', new_id)
                root_b.append(c)

            if comment_part_b is not None:
                comment_part_b._blob = etree.tostring(root_b, xml_declaration=True, encoding='UTF-8', standalone=True)
            return id_remap
        except Exception:
            return {}

    comment_id_remap = _merge_comments_from_a()

    def remap_comment_ids_in_element(el):
        """Remap comment IDs in paragraph elements copied from doc_a."""
        if not comment_id_remap:
            return
        for tag_name in ('commentRangeStart', 'commentRangeEnd', 'commentReference'):
            for node in el.findall(f'.//{{{W}}}{tag_name}'):
                old_id = node.get(f'{{{W}}}id', '')
                if old_id in comment_id_remap:
                    node.set(f'{{{W}}}id', comment_id_remap[old_id])

    # ── Build redline body ──
    import shutil
    work_path = os.path.join(tmpdir, '_work.docx')
    shutil.copy2(filepath_b, work_path)
    out_doc = DocxDocument(work_path)

    # ── Collect valid relationship IDs from out_doc ──
    # Elements copied from doc_a may reference rIds (images, hyperlinks) that
    # only exist in doc_a. We must strip these to prevent DOCX corruption.
    out_doc_rids = set()
    try:
        for rel_key in out_doc.element.part.rels:
            out_doc_rids.add(rel_key)
    except Exception:
        pass

    def _sanitize_element_from_a(el):
        """Remove all references from a doc_a element that could corrupt out_doc.

        Strips: footnoteReference, endnoteReference, drawings/images,
        hyperlinks with broken rIds, and other relationship-dependent elements.
        This is safer than trying to merge all parts from doc_a.
        """
        WP_NS = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
        V_NS = 'urn:schemas-microsoft-com:vml'
        O_NS = 'urn:schemas-microsoft-com:office:office'

        # 1. Strip footnote references (point to footnotes part that belongs to doc_a)
        for fn_ref in el.findall(f'.//{{{W}}}footnoteReference'):
            parent = fn_ref.getparent()
            if parent is not None:
                parent.remove(fn_ref)

        # 2. Strip endnote references
        for en_ref in el.findall(f'.//{{{W}}}endnoteReference'):
            parent = en_ref.getparent()
            if parent is not None:
                parent.remove(en_ref)

        # 3. Strip drawing elements (images, shapes - reference rIds for media)
        for drawing in el.findall(f'.//{{{W}}}drawing'):
            parent = drawing.getparent()
            if parent is not None:
                parent.remove(drawing)

        # 4. Strip VML picture/object elements (legacy image format)
        for pict in el.findall(f'.//{{{W}}}pict'):
            parent = pict.getparent()
            if parent is not None:
                parent.remove(pict)

        # 5. Strip OLE objects
        for obj in el.findall(f'.//{{{W}}}object'):
            parent = obj.getparent()
            if parent is not None:
                parent.remove(obj)

        # 6. Handle hyperlinks: keep text runs but remove wrapper if rId is broken
        for hyperlink in list(el.findall(f'.//{{{W}}}hyperlink')):
            r_id = hyperlink.get(f'{{{R_NS}}}id', '')
            if r_id and r_id not in out_doc_rids:
                # Broken hyperlink - unwrap: move children up, remove wrapper
                parent = hyperlink.getparent()
                if parent is not None:
                    idx = list(parent).index(hyperlink)
                    for child in list(hyperlink):
                        hyperlink.remove(child)
                        parent.insert(idx, child)
                        idx += 1
                    parent.remove(hyperlink)

        # 7. Strip field codes that reference external elements (TOC, REF, etc.
        #    can reference bookmarks/fields that don't exist in out_doc)
        #    Keep simple field codes but remove complex cross-doc references

        # 8. Strip numbering references that don't exist in out_doc
        #    (complex SPAs have custom numbering schemes)
        for numPr in el.findall(f'.//{{{W}}}numPr'):
            numId_el = numPr.find(f'{{{W}}}numId')
            if numId_el is not None:
                num_val = numId_el.get(f'{{{W}}}val', '0')
                # Keep numId 0 (no numbering), strip others from doc_a
                # since we can't guarantee they exist in out_doc
                if num_val != '0':
                    parent = numPr.getparent()
                    if parent is not None:
                        parent.remove(numPr)

    body = out_doc.element.body
    # Remove all paragraphs and tables from body, but keep sectPr and other structural elements
    for child in list(body):
        tag_local = etree.QName(child.tag).localname if '}' in child.tag else child.tag
        if tag_local in ('p', 'tbl'):
            # Don't remove the last paragraph if it contains sectPr
            sect_pr = child.find(f'{{{W}}}pPr/{{{W}}}sectPr')
            if sect_pr is None:
                sect_pr = child.find(f'{{{W}}}sectPr')
            if sect_pr is not None:
                continue  # Keep paragraph with section properties
            body.remove(child)

    sm = difflib.SequenceMatcher(None, paras_a, paras_b, autojunk=False)
    comment_id_counter = [0]

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for idx in range(j1, j2):
                p_el = etree.fromstring(etree.tostring(doc_b.paragraphs[idx]._element))
                body.append(p_el)

        elif tag == 'replace':
            for idx in range(max(i2 - i1, j2 - j1)):
                old_idx = i1 + idx if (i1 + idx) < i2 else None
                new_idx = j1 + idx if (j1 + idx) < j2 else None
                old_text = paras_a[old_idx] if old_idx is not None else ''
                new_text = paras_b[new_idx] if new_idx is not None else ''

                p_el = etree.SubElement(body, f'{{{W}}}p')
                # Copy paragraph properties from new version (or old)
                if new_idx is not None:
                    src_ppr = doc_b.paragraphs[new_idx]._element.find(f'{{{W}}}pPr')
                    if src_ppr is not None:
                        p_el.append(etree.fromstring(etree.tostring(src_ppr)))
                elif old_idx is not None:
                    src_ppr = doc_a.paragraphs[old_idx]._element.find(f'{{{W}}}pPr')
                    if src_ppr is not None:
                        ppr_copy = etree.fromstring(etree.tostring(src_ppr))
                        _sanitize_element_from_a(ppr_copy)
                        p_el.append(ppr_copy)

                # Get run formatting from source documents
                rpr_a = None
                rpr_b = None
                if old_idx is not None:
                    runs_a = get_runs_with_format(doc_a.paragraphs[old_idx])
                    if runs_a:
                        rpr_a = runs_a[0][1]
                if new_idx is not None:
                    runs_b = get_runs_with_format(doc_b.paragraphs[new_idx])
                    if runs_b:
                        rpr_b = runs_b[0][1]

                if old_text and new_text:
                    cnum = record_change('Ersetzung', old_text, new_text, new_idx or old_idx)
                    add_bookmark(p_el, cnum)
                    # Word-level diff
                    words_a = re.findall(r'\S+|\s+', old_text)
                    words_b = re.findall(r'\S+|\s+', new_text)
                    wsm = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)

                    for wtag, wi1, wi2, wj1, wj2 in wsm.get_opcodes():
                        if wtag == 'equal':
                            r = make_run_element(''.join(words_b[wj1:wj2]), rpr_b)
                            p_el.append(r)
                        elif wtag == 'replace':
                            r_del = make_run_element(''.join(words_a[wi1:wi2]), rpr_a)
                            p_el.append(wrap_in_del(r_del))
                            r_ins = make_run_element(''.join(words_b[wj1:wj2]), rpr_b)
                            p_el.append(wrap_in_ins(r_ins))
                        elif wtag == 'delete':
                            r_del = make_run_element(''.join(words_a[wi1:wi2]), rpr_a)
                            p_el.append(wrap_in_del(r_del))
                        elif wtag == 'insert':
                            r_ins = make_run_element(''.join(words_b[wj1:wj2]), rpr_b)
                            p_el.append(wrap_in_ins(r_ins))

                    # Carry over non-run elements and field-containing runs from both sources
                    non_run_tags = ('fldSimple', 'commentRangeStart', 'commentRangeEnd',
                                    'bookmarkStart', 'bookmarkEnd')
                    if old_idx is not None:
                        for child in doc_a.paragraphs[old_idx]._element:
                            local = etree.QName(child.tag).localname if '}' in child.tag else child.tag
                            if local in non_run_tags:
                                copied = etree.fromstring(etree.tostring(child))
                                remap_comment_ids_in_element(copied)
                                p_el.append(copied)
                            elif local == 'r':
                                # Only copy field-code runs (fldChar, instrText)
                                # Skip footnoteReference/endnoteReference — they reference
                                # parts that don't exist in out_doc and cause corruption
                                has_field = child.find(f'{{{W}}}fldChar') is not None
                                has_instr = child.find(f'{{{W}}}instrText') is not None
                                if has_field or has_instr:
                                    copied_run = etree.fromstring(etree.tostring(child))
                                    _sanitize_element_from_a(copied_run)
                                    p_el.append(copied_run)
                    if new_idx is not None:
                        for child in doc_b.paragraphs[new_idx]._element:
                            local = etree.QName(child.tag).localname if '}' in child.tag else child.tag
                            if local in non_run_tags:
                                p_el.append(etree.fromstring(etree.tostring(child)))
                            elif local == 'r':
                                has_field = child.find(f'{{{W}}}fldChar') is not None
                                has_instr = child.find(f'{{{W}}}instrText') is not None
                                has_fnref = child.find(f'{{{W}}}footnoteReference') is not None
                                has_enref = child.find(f'{{{W}}}endnoteReference') is not None
                                if has_field or has_instr or has_fnref or has_enref:
                                    p_el.append(etree.fromstring(etree.tostring(child)))
                elif old_text:
                    cnum = record_change('Löschung', old_text, '', old_idx)
                    add_bookmark(p_el, cnum)
                    r_del = make_run_element(old_text, rpr_a)
                    p_el.append(wrap_in_del(r_del))
                elif new_text:
                    cnum = record_change('Einfügung', '', new_text, new_idx)
                    add_bookmark(p_el, cnum)
                    r_ins = make_run_element(new_text, rpr_b)
                    p_el.append(wrap_in_ins(r_ins))

        elif tag == 'delete':
            for idx in range(i1, i2):
                if idx in moved_from_a:
                    cnum = record_change('Verschoben (Quelle)', paras_a[idx], '', idx)
                else:
                    cnum = record_change('Löschung', paras_a[idx], '', idx)

                # Copy full paragraph from doc_a (preserves comment refs, footnote refs, field codes)
                p_el = etree.fromstring(etree.tostring(doc_a.paragraphs[idx]._element))
                remap_comment_ids_in_element(p_el)
                _sanitize_element_from_a(p_el)
                # Wrap all runs in deletion marks (collect first, then replace)
                runs_with_pos = []
                for r_el in p_el.findall(f'{{{W}}}r'):
                    parent = r_el.getparent()
                    pos = list(parent).index(r_el)
                    runs_with_pos.append((parent, pos, r_el))
                for parent, pos, r_el in reversed(runs_with_pos):
                    parent.remove(r_el)
                    del_wrapper = wrap_in_del(r_el)
                    parent.insert(pos, del_wrapper)
                add_bookmark(p_el, cnum)
                body.append(p_el)

                # Mark paragraph mark as deleted
                ppr_del = p_el.find(f'{{{W}}}pPr')
                if ppr_del is None:
                    ppr_del = etree.SubElement(p_el, f'{{{W}}}pPr')
                rpr_del = etree.SubElement(ppr_del, f'{{{W}}}rPr')
                del_elem = etree.SubElement(rpr_del, f'{{{W}}}del')
                del_elem.set(f'{{{W}}}id', str(next(rev_id_gen)))
                del_elem.set(f'{{{W}}}author', author)
                del_elem.set(f'{{{W}}}date', date_str)

        elif tag == 'insert':
            for idx in range(j1, j2):
                if idx in moved_to_b:
                    cnum = record_change('Verschoben (Ziel)', '', paras_b[idx], idx)
                else:
                    cnum = record_change('Einfügung', '', paras_b[idx], idx)

                # Copy full paragraph from doc_b (preserves comment refs, footnote refs, field codes)
                p_el = etree.fromstring(etree.tostring(doc_b.paragraphs[idx]._element))
                # Wrap all runs in insertion marks (collect first, then replace)
                runs_with_pos = []
                for r_el in p_el.findall(f'{{{W}}}r'):
                    parent = r_el.getparent()
                    pos = list(parent).index(r_el)
                    runs_with_pos.append((parent, pos, r_el))
                for parent, pos, r_el in reversed(runs_with_pos):
                    parent.remove(r_el)
                    ins_wrapper = wrap_in_ins(r_el)
                    parent.insert(pos, ins_wrapper)
                add_bookmark(p_el, cnum)
                body.append(p_el)


    # ── Table-level comparison ──
    tables_a = doc_a.tables
    tables_b = doc_b.tables
    num_tables = max(len(tables_a), len(tables_b))

    def _wrap_all_runs_in_element_as_ins(element):
        """Wrap all w:r elements inside an XML element tree with w:ins."""
        runs_with_pos = []
        for r_el in element.findall(f'.//{{{W}}}r'):
            parent = r_el.getparent()
            pos = list(parent).index(r_el)
            runs_with_pos.append((parent, pos, r_el))
        for parent, pos, r_el in reversed(runs_with_pos):
            parent.remove(r_el)
            ins_wrapper = wrap_in_ins(r_el)
            parent.insert(pos, ins_wrapper)

    def _wrap_all_runs_in_element_as_del(element):
        """Wrap all w:r elements inside an XML element tree with w:del."""
        runs_with_pos = []
        for r_el in element.findall(f'.//{{{W}}}r'):
            parent = r_el.getparent()
            pos = list(parent).index(r_el)
            runs_with_pos.append((parent, pos, r_el))
        for parent, pos, r_el in reversed(runs_with_pos):
            parent.remove(r_el)
            del_wrapper = wrap_in_del(r_el)
            parent.insert(pos, del_wrapper)

    def _mark_row_paragraph_marks_deleted(tr_el):
        """Mark paragraph marks in a row as deleted (w:pPr/w:rPr/w:del)."""
        for p_el in tr_el.findall(f'.//{{{W}}}p'):
            ppr = p_el.find(f'{{{W}}}pPr')
            if ppr is None:
                ppr = etree.SubElement(p_el, f'{{{W}}}pPr')
            rpr = ppr.find(f'{{{W}}}rPr')
            if rpr is None:
                rpr = etree.SubElement(ppr, f'{{{W}}}rPr')
            del_elem = etree.SubElement(rpr, f'{{{W}}}del')
            del_elem.set(f'{{{W}}}id', str(next(rev_id_gen)))
            del_elem.set(f'{{{W}}}author', author)
            del_elem.set(f'{{{W}}}date', date_str)

    for tbl_idx in range(num_tables):
        tbl_a = tables_a[tbl_idx] if tbl_idx < len(tables_a) else None
        tbl_b = tables_b[tbl_idx] if tbl_idx < len(tables_b) else None
        tbl_label = f'Tabelle {tbl_idx + 1}'

        if tbl_a is None and tbl_b is not None:
            # Entire table is new (insertion)
            record_change('Tabellenänderung', '', f'{tbl_label}: Gesamte Tabelle eingefügt', 0)
            tbl_el = etree.fromstring(etree.tostring(tbl_b._tbl))
            _wrap_all_runs_in_element_as_ins(tbl_el)
            body.append(tbl_el)

        elif tbl_b is None and tbl_a is not None:
            # Entire table was deleted
            record_change('Tabellenänderung', f'{tbl_label}: Gesamte Tabelle gelöscht', '', 0)
            tbl_el = etree.fromstring(etree.tostring(tbl_a._tbl))
            _sanitize_element_from_a(tbl_el)
            _wrap_all_runs_in_element_as_del(tbl_el)
            for tr_el in tbl_el.findall(f'{{{W}}}tr'):
                _mark_row_paragraph_marks_deleted(tr_el)
            body.append(tbl_el)

        else:
            # Both tables exist - compare cell-by-cell
            tbl_el = etree.fromstring(etree.tostring(tbl_b._tbl))

            num_rows_a = len(tbl_a.rows)
            num_rows_b = len(tbl_b.rows)

            def _row_texts(table, n_rows):
                """Get concatenated cell text per row for sequence matching."""
                result = []
                for ri in range(n_rows):
                    cells_text = []
                    for ci in range(len(table.rows[ri].cells)):
                        cells_text.append(table.rows[ri].cells[ci].text or '')
                    result.append('\t'.join(cells_text))
                return result

            rtexts_a = _row_texts(tbl_a, num_rows_a)
            rtexts_b = _row_texts(tbl_b, num_rows_b)

            row_sm = difflib.SequenceMatcher(None, rtexts_a, rtexts_b, autojunk=False)
            row_opcodes = row_sm.get_opcodes()

            # Remove all existing tr elements from the cloned table
            for existing_tr in list(tbl_el.findall(f'{{{W}}}tr')):
                tbl_el.remove(existing_tr)

            for rtag, ri1, ri2, rj1, rj2 in row_opcodes:
                if rtag == 'equal':
                    for offset in range(rj2 - rj1):
                        a_ri = ri1 + offset
                        b_ri = rj1 + offset
                        row_b_obj = tbl_b.rows[b_ri]
                        row_a_obj = tbl_a.rows[a_ri]
                        tr_el = etree.fromstring(etree.tostring(row_b_obj._tr))
                        tc_els = tr_el.findall(f'{{{W}}}tc')

                        num_cells_a = len(row_a_obj.cells)
                        num_cells_b = len(row_b_obj.cells)

                        for ci in range(min(num_cells_a, num_cells_b)):
                            text_a = row_a_obj.cells[ci].text or ''
                            text_b = row_b_obj.cells[ci].text or ''
                            if text_a != text_b and ci < len(tc_els):
                                record_change(
                                    'Tabellenänderung', text_a, text_b, 0)

                                tc_el = tc_els[ci]
                                for p_existing in list(tc_el.findall(f'{{{W}}}p')):
                                    tc_el.remove(p_existing)

                                p_el = etree.SubElement(tc_el, f'{{{W}}}p')

                                rpr_a_xml = None
                                rpr_b_xml = None
                                for p_src in row_a_obj.cells[ci].paragraphs:
                                    runs_src = get_runs_with_format(p_src)
                                    if runs_src:
                                        rpr_a_xml = runs_src[0][1]
                                        break
                                for p_src in row_b_obj.cells[ci].paragraphs:
                                    runs_src = get_runs_with_format(p_src)
                                    if runs_src:
                                        rpr_b_xml = runs_src[0][1]
                                        break

                                words_a = re.findall(r'\S+|\s+', text_a)
                                words_b = re.findall(r'\S+|\s+', text_b)
                                wsm = difflib.SequenceMatcher(
                                    None, words_a, words_b, autojunk=False)

                                for wtag, wi1, wi2, wj1, wj2 in wsm.get_opcodes():
                                    if wtag == 'equal':
                                        r_run = make_run_element(
                                            ''.join(words_b[wj1:wj2]), rpr_b_xml)
                                        p_el.append(r_run)
                                    elif wtag == 'replace':
                                        r_del = make_run_element(
                                            ''.join(words_a[wi1:wi2]), rpr_a_xml)
                                        p_el.append(wrap_in_del(r_del))
                                        r_ins = make_run_element(
                                            ''.join(words_b[wj1:wj2]), rpr_b_xml)
                                        p_el.append(wrap_in_ins(r_ins))
                                    elif wtag == 'delete':
                                        r_del = make_run_element(
                                            ''.join(words_a[wi1:wi2]), rpr_a_xml)
                                        p_el.append(wrap_in_del(r_del))
                                    elif wtag == 'insert':
                                        r_ins = make_run_element(
                                            ''.join(words_b[wj1:wj2]), rpr_b_xml)
                                        p_el.append(wrap_in_ins(r_ins))

                        tbl_el.append(tr_el)

                elif rtag == 'replace':
                    for idx in range(ri1, ri2):
                        tr_el = etree.fromstring(etree.tostring(tbl_a.rows[idx]._tr))
                        _sanitize_element_from_a(tr_el)
                        _wrap_all_runs_in_element_as_del(tr_el)
                        _mark_row_paragraph_marks_deleted(tr_el)
                        record_change('Tabellenänderung', rtexts_a[idx][:120], '', 0)
                        tbl_el.append(tr_el)

                    for idx in range(rj1, rj2):
                        tr_el = etree.fromstring(etree.tostring(tbl_b.rows[idx]._tr))
                        _wrap_all_runs_in_element_as_ins(tr_el)
                        record_change('Tabellenänderung', '', rtexts_b[idx][:120], 0)
                        tbl_el.append(tr_el)

                elif rtag == 'delete':
                    for idx in range(ri1, ri2):
                        tr_el = etree.fromstring(etree.tostring(tbl_a.rows[idx]._tr))
                        _sanitize_element_from_a(tr_el)
                        _wrap_all_runs_in_element_as_del(tr_el)
                        _mark_row_paragraph_marks_deleted(tr_el)
                        record_change('Tabellenänderung', rtexts_a[idx][:120], '', 0)
                        tbl_el.append(tr_el)

                elif rtag == 'insert':
                    for idx in range(rj1, rj2):
                        tr_el = etree.fromstring(etree.tostring(tbl_b.rows[idx]._tr))
                        _wrap_all_runs_in_element_as_ins(tr_el)
                        record_change('Tabellenänderung', '', rtexts_b[idx][:120], 0)
                        tbl_el.append(tr_el)

            body.append(tbl_el)

    out_path = os.path.join(tmpdir, 'redline.docx')
    out_doc.save(out_path)
    return out_path


def _generate_docx_report(filepath_a, filepath_b, tmpdir):
    """
    Generate a separate DOCX change report with:
    - Änderungsstatistik (statistics table)
    - Änderungsliste with colored markup (red strikethrough / blue underline / purple moved)
    Uses python-docx for clean, well-formatted output.
    """
    from docx import Document as DocxDocument
    from docx.shared import Pt, RGBColor, Inches, Cm, Emu
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    import difflib
    import re
    from datetime import datetime
    from collections import Counter

    doc_a = DocxDocument(filepath_a)
    doc_b = DocxDocument(filepath_b)

    # Extract ALL text including tables
    def get_all_text_blocks(doc):
        """Extract text from paragraphs AND table cells, preserving order."""
        blocks = []
        body = doc.element.body
        W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        for child in body:
            tag = etree.QName(child.tag).localname if '}' in child.tag else child.tag
            if tag == 'p':
                text = ''.join(t.text or '' for t in child.iter(f'{{{W}}}t'))
                blocks.append(text)
            elif tag == 'tbl':
                for row in child.iter(f'{{{W}}}tr'):
                    row_texts = []
                    for cell in row.iter(f'{{{W}}}tc'):
                        cell_text = ''.join(t.text or '' for t in cell.iter(f'{{{W}}}t'))
                        row_texts.append(cell_text.strip())
                    combined = ' | '.join(t for t in row_texts if t)
                    if combined:
                        blocks.append(f'[Tabelle] {combined}')
        return blocks

    from lxml import etree
    paras_a = get_all_text_blocks(doc_a)
    paras_b = get_all_text_blocks(doc_b)

    # ── Move detection ──
    sm_pre = difflib.SequenceMatcher(None, paras_a, paras_b, autojunk=False)
    deleted_paras = {}
    inserted_paras = {}
    for tag, i1, i2, j1, j2 in sm_pre.get_opcodes():
        if tag == 'delete':
            for idx in range(i1, i2):
                txt = paras_a[idx].strip()
                if txt and len(txt) > 10:
                    deleted_paras.setdefault(txt, []).append(idx)
        elif tag == 'insert':
            for idx in range(j1, j2):
                txt = paras_b[idx].strip()
                if txt and len(txt) > 10:
                    inserted_paras.setdefault(txt, []).append(idx)

    moved_from_a = set()
    moved_to_b = set()
    for txt in deleted_paras:
        if txt in inserted_paras:
            for a_idx, b_idx in zip(deleted_paras[txt], inserted_paras[txt]):
                moved_from_a.add(a_idx)
                moved_to_b.add(b_idx)

    # ── Collect all changes ──
    all_changes = []
    change_counter = [0]

    def record_change(change_type, old_text='', new_text=''):
        change_counter[0] += 1
        all_changes.append({
            'num': change_counter[0],
            'type': change_type,
            'old': old_text or '',
            'new': new_text or '',
        })

    sm = difflib.SequenceMatcher(None, paras_a, paras_b, autojunk=False)
    opcodes = sm.get_opcodes()

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'replace':
            for idx in range(max(i2 - i1, j2 - j1)):
                old_idx = i1 + idx if (i1 + idx) < i2 else None
                new_idx = j1 + idx if (j1 + idx) < j2 else None
                old_text = paras_a[old_idx] if old_idx is not None else ''
                new_text = paras_b[new_idx] if new_idx is not None else ''
                if old_text and new_text:
                    record_change('Ersetzung', old_text, new_text)
                elif old_text:
                    record_change('Löschung', old_text)
                elif new_text:
                    record_change('Einfügung', new_text=new_text)
        elif tag == 'delete':
            for idx in range(i1, i2):
                if idx in moved_from_a:
                    record_change('Verschoben (Quelle)', paras_a[idx])
                else:
                    record_change('Löschung', paras_a[idx])
        elif tag == 'insert':
            for idx in range(j1, j2):
                if idx in moved_to_b:
                    record_change('Verschoben (Ziel)', new_text=paras_b[idx])
                else:
                    record_change('Einfügung', new_text=paras_b[idx])

    type_counts = Counter(c['type'] for c in all_changes)
    total_changes = len(all_changes)

    # ── Colors ──
    CLR_INS = RGBColor(0x15, 0x65, 0xC0)   # blue
    CLR_DEL = RGBColor(0xC6, 0x28, 0x28)   # red
    CLR_MOVE = RGBColor(0x6A, 0x1B, 0x9A)  # purple
    CLR_TITLE = RGBColor(0x1F, 0x38, 0x64)
    CLR_GREY = RGBColor(0x66, 0x66, 0x66)
    CLR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    CLR_FMT = RGBColor(0xE6, 0x51, 0x00)    # orange for formatting changes
    CLR_TBL = RGBColor(0x00, 0x69, 0x5C)    # teal for table changes

    type_bg_colors = {
        'Einfügung': 'E8F5E9', 'Löschung': 'FFEBEE', 'Ersetzung': 'FFF8E1',
        'Verschoben (Quelle)': 'F3E5F5', 'Verschoben (Ziel)': 'F3E5F5',
        'Formatierung': 'FFF3E0', 'Tabellenänderung': 'E0F2F1',
    }

    def set_cell_bg(cell, hex_color):
        """Set cell background color."""
        shading = OxmlElement('w:shd')
        shading.set(qn('w:val'), 'clear')
        shading.set(qn('w:fill'), hex_color)
        cell._tc.get_or_add_tcPr().append(shading)

    def add_markup_runs(paragraph, change):
        """Add colored markup runs to a paragraph based on change type."""
        ctype = change['type']
        old = change['old']
        new = change['new']

        if ctype == 'Ersetzung' and old and new:
            # Word-level diff with colored markup
            words_a = re.findall(r'\S+|\s+', old)
            words_b = re.findall(r'\S+|\s+', new)
            wsm = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)
            for wtag, wi1, wi2, wj1, wj2 in wsm.get_opcodes():
                if wtag == 'equal':
                    run = paragraph.add_run(''.join(words_b[wj1:wj2]))
                    run.font.size = Pt(8)
                elif wtag == 'replace':
                    run_del = paragraph.add_run(''.join(words_a[wi1:wi2]))
                    run_del.font.size = Pt(8)
                    run_del.font.color.rgb = CLR_DEL
                    run_del.font.strike = True
                    run_ins = paragraph.add_run(''.join(words_b[wj1:wj2]))
                    run_ins.font.size = Pt(8)
                    run_ins.font.color.rgb = CLR_INS
                    run_ins.font.underline = True
                elif wtag == 'delete':
                    run_del = paragraph.add_run(''.join(words_a[wi1:wi2]))
                    run_del.font.size = Pt(8)
                    run_del.font.color.rgb = CLR_DEL
                    run_del.font.strike = True
                elif wtag == 'insert':
                    run_ins = paragraph.add_run(''.join(words_b[wj1:wj2]))
                    run_ins.font.size = Pt(8)
                    run_ins.font.color.rgb = CLR_INS
                    run_ins.font.underline = True

        elif ctype in ('Löschung', 'Verschoben (Quelle)'):
            color = CLR_MOVE if 'Verschoben' in ctype else CLR_DEL
            run = paragraph.add_run(old[:200])
            run.font.size = Pt(8)
            run.font.color.rgb = color
            run.font.strike = True
            if 'Verschoben' in ctype:
                tag_run = paragraph.add_run(' [verschoben]')
                tag_run.font.size = Pt(7)
                tag_run.font.color.rgb = CLR_MOVE
                tag_run.font.italic = True

        elif ctype in ('Einfügung', 'Verschoben (Ziel)'):
            color = CLR_MOVE if 'Verschoben' in ctype else CLR_INS
            run = paragraph.add_run(new[:200])
            run.font.size = Pt(8)
            run.font.color.rgb = color
            run.font.underline = True
            if 'Verschoben' in ctype:
                tag_run = paragraph.add_run(' [hierhin verschoben]')
                tag_run.font.size = Pt(7)
                tag_run.font.color.rgb = CLR_MOVE
                tag_run.font.italic = True
        elif ctype == 'Formatierung':
            # Show the text context in normal style
            text_preview = (old or new or '')[:120]
            if text_preview:
                run = paragraph.add_run(text_preview)
                run.font.size = Pt(8)
                run.font.color.rgb = CLR_GREY
            # Show the formatting change description in orange
            # The 'new' field contains the description of what changed
            if new and new != text_preview:
                desc_run = paragraph.add_run(f'\n{new}')
                desc_run.font.size = Pt(7)
                desc_run.font.color.rgb = CLR_FMT
                desc_run.font.italic = True
        else:
            run = paragraph.add_run(old or new or '—')
            run.font.size = Pt(8)

    # ── Build report document ──
    report = DocxDocument()

    # Narrow margins
    for section in report.sections:
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)

    # Title
    p_title = report.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_title.add_run('Änderungsbericht')
    run.font.size = Pt(22)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x15, 0x65, 0xC0)

    p_sub = report.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_sub.add_run('MyCompare — Dokumentenvergleich')
    run.font.size = Pt(11)
    run.font.color.rgb = CLR_GREY

    p_date = report.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_date.add_run(f'Erstellt am: {datetime.now().strftime("%d.%m.%Y %H:%M")}')
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    # ─── Legende ───
    p_h = report.add_paragraph()
    run = p_h.add_run('Legende')
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = CLR_TITLE

    legend_items = [
        ('Eingefügt', 'Text der in der neuen Version hinzugefügt wurde', CLR_INS, False, True),
        ('Gelöscht', 'Text der aus der alten Version entfernt wurde', CLR_DEL, True, False),
        ('Ersetzung', 'Gelöschter Text (rot) gefolgt von neuem Text (blau)', CLR_GREY, False, False),
        ('Verschoben', 'Text der an eine andere Stelle verschoben wurde', CLR_MOVE, False, False),
        ('Formatierung', 'Gleicher Text, aber Formatierung geändert (z.B. Fett, Schriftgröße)', CLR_FMT, False, False),
        ('Tabellenänderung', 'Änderungen innerhalb von Tabellenzellen, Zeilen oder ganzen Tabellen', CLR_TBL, False, False),
    ]
    for label, desc, color, strike, underline in legend_items:
        p = report.add_paragraph()
        r1 = p.add_run(f'  {label}')
        r1.font.size = Pt(10)
        r1.font.bold = True
        r1.font.color.rgb = color
        if strike:
            r1.font.strike = True
        if underline:
            r1.font.underline = True
        r2 = p.add_run(f'  — {desc}')
        r2.font.size = Pt(9)
        r2.font.color.rgb = CLR_GREY

    # ─── Änderungsstatistik ───
    p_h = report.add_paragraph()
    run = p_h.add_run('Änderungsstatistik')
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = CLR_TITLE

    stats_table = report.add_table(rows=1, cols=2)
    stats_table.alignment = WD_TABLE_ALIGNMENT.LEFT
    hdr = stats_table.rows[0].cells
    hdr[0].text = 'Änderungstyp'
    hdr[1].text = 'Anzahl'
    for cell in hdr:
        set_cell_bg(cell, '1565C0')
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.color.rgb = CLR_WHITE
                r.font.size = Pt(9)

    for ctype, count in type_counts.most_common():
        row = stats_table.add_row().cells
        row[0].text = ctype
        row[1].text = str(count)
        bg = type_bg_colors.get(ctype, 'F5F5F5')
        for cell in row:
            set_cell_bg(cell, bg)
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9)

    total_row = stats_table.add_row().cells
    total_row[0].text = 'Gesamt'
    total_row[1].text = str(total_changes)
    for cell in total_row:
        set_cell_bg(cell, 'E3F2FD')
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(10)

    # ─── Änderungsliste with colored markup ───
    report.add_page_break()

    p_h = report.add_paragraph()
    run = p_h.add_run('Änderungsliste')
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = CLR_TITLE

    changes_table = report.add_table(rows=1, cols=4)
    changes_table.alignment = WD_TABLE_ALIGNMENT.LEFT
    hdr = changes_table.rows[0].cells
    hdr[0].text = 'Nr.'
    hdr[1].text = 'Typ'
    hdr[2].text = 'Alter Text'
    hdr[3].text = 'Neuer Text'
    for cell in hdr:
        set_cell_bg(cell, '1565C0')
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.color.rgb = CLR_WHITE
                r.font.size = Pt(9)

    for change in all_changes:
        row = changes_table.add_row().cells
        # Nr.
        row[0].text = str(change['num'])
        for p in row[0].paragraphs:
            for r in p.runs:
                r.font.size = Pt(8)

        # Typ
        row[1].text = change['type']
        type_color = {
            'Einfügung': CLR_INS, 'Löschung': CLR_DEL,
            'Ersetzung': CLR_GREY,
            'Verschoben (Quelle)': CLR_MOVE, 'Verschoben (Ziel)': CLR_MOVE,
            'Formatierung': CLR_FMT, 'Tabellenänderung': CLR_TBL,
        }.get(change['type'], CLR_GREY)
        for p in row[1].paragraphs:
            for r in p.runs:
                r.font.size = Pt(8)
                r.font.bold = True
                r.font.color.rgb = type_color

        # Alter Text — plain, with strikethrough for deletions
        old_para = row[2].paragraphs[0]
        old_para.clear()
        old_text = change['old'][:200] if change['old'] else '—'
        if change['type'] in ('Löschung', 'Verschoben (Quelle)'):
            color = CLR_MOVE if 'Verschoben' in change['type'] else CLR_DEL
            r = old_para.add_run(old_text)
            r.font.size = Pt(8)
            r.font.color.rgb = color
            r.font.strike = True
        else:
            r = old_para.add_run(old_text)
            r.font.size = Pt(8)

        # Neuer Text — with colored markup
        new_para = row[3].paragraphs[0]
        new_para.clear()
        add_markup_runs(new_para, change)

        # Row background
        bg = type_bg_colors.get(change['type'], 'F5F5F5')
        for cell in row:
            set_cell_bg(cell, bg)

    # No more truncation - all changes are included

    # Set column widths
    for row in changes_table.rows:
        row.cells[0].width = Cm(1)
        row.cells[1].width = Cm(2.5)
        row.cells[2].width = Cm(7)
        row.cells[3].width = Cm(7)

    # ─── Vollständigkeitsprüfung ───
    report.add_page_break()
    p_h = report.add_paragraph()
    run = p_h.add_run('Vollständigkeitsprüfung')
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = CLR_TITLE

    # Count text blocks
    total_blocks_a = len(paras_a)
    total_blocks_b = len(paras_b)
    table_changes = sum(1 for c in all_changes if c.get('old', '').startswith('[Tabelle]') or c.get('new', '').startswith('[Tabelle]'))
    text_changes = total_changes - table_changes

    # Compute coverage: how many blocks from A and B were matched by the diff
    equal_blocks = sum(i2 - i1 for tag, i1, i2, j1, j2 in opcodes if tag == 'equal')
    changed_blocks_a = sum(i2 - i1 for tag, i1, i2, j1, j2 in opcodes if tag in ('replace', 'delete'))
    changed_blocks_b = sum(j2 - j1 for tag, i1, i2, j1, j2 in opcodes if tag in ('replace', 'insert'))
    coverage_a = equal_blocks + changed_blocks_a
    coverage_b = equal_blocks + changed_blocks_b

    check_items = [
        ('Textblöcke Version A (alt)', str(total_blocks_a), ''),
        ('Textblöcke Version B (neu)', str(total_blocks_b), ''),
        ('Erfasste Blöcke aus Version A', f'{coverage_a}/{total_blocks_a}',
         'OK' if coverage_a == total_blocks_a else f'WARNUNG: {total_blocks_a - coverage_a} nicht erfasst'),
        ('Erfasste Blöcke aus Version B', f'{coverage_b}/{total_blocks_b}',
         'OK' if coverage_b == total_blocks_b else f'WARNUNG: {total_blocks_b - coverage_b} nicht erfasst'),
        ('Erkannte Änderungen gesamt', str(total_changes), ''),
        ('  davon Textänderungen', str(text_changes), ''),
        ('  davon Tabellenänderungen', str(table_changes), ''),
        ('Alle Änderungen im Bericht', f'{len(all_changes)}/{total_changes}',
         'VOLLSTÄNDIG' if len(all_changes) == total_changes else f'UNVOLLSTÄNDIG'),
    ]

    verify_table = report.add_table(rows=1, cols=3)
    verify_table.alignment = WD_TABLE_ALIGNMENT.LEFT
    hdr = verify_table.rows[0].cells
    hdr[0].text = 'Prüfpunkt'
    hdr[1].text = 'Wert'
    hdr[2].text = 'Status'
    for cell in hdr:
        set_cell_bg(cell, '1565C0')
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.color.rgb = CLR_WHITE
                r.font.size = Pt(9)

    for label, value, status in check_items:
        row = verify_table.add_row().cells
        row[0].text = label
        row[1].text = value
        row[2].text = status
        for p in row[0].paragraphs:
            for r in p.runs:
                r.font.size = Pt(9)
        for p in row[1].paragraphs:
            for r in p.runs:
                r.font.size = Pt(9)
                r.font.bold = True
        for p in row[2].paragraphs:
            for r in p.runs:
                r.font.size = Pt(9)
                if 'OK' in status or 'VOLLSTÄNDIG' == status:
                    r.font.color.rgb = RGBColor(0x22, 0xA3, 0x4A)
                    r.font.bold = True
                elif 'WARNUNG' in status or 'UNVOLLSTÄNDIG' in status:
                    r.font.color.rgb = CLR_DEL
                    r.font.bold = True

    for row in verify_table.rows:
        row.cells[0].width = Cm(6)
        row.cells[1].width = Cm(4)
        row.cells[2].width = Cm(6)

    # ─── Bildvergleich (Image Changes) ───
    try:
        imgs_a = extract_images(filepath_a, 'docx')
        imgs_b = extract_images(filepath_b, 'docx')
        image_changes = compare_images(imgs_a, imgs_b)
        # Only include non-unchanged images
        changed_images = [ic for ic in image_changes if ic['type'] != 'unchanged']

        if changed_images:
            report.add_page_break()

            p_h = report.add_paragraph()
            run = p_h.add_run('Bildvergleich')
            run.font.size = Pt(14)
            run.font.bold = True
            run.font.color.rgb = CLR_TITLE

            p_desc = report.add_paragraph()
            run = p_desc.add_run(
                f'{len(changed_images)} Bildänderung(en) gefunden '
                f'(von {len(image_changes)} Bildern insgesamt).'
            )
            run.font.size = Pt(9)
            run.font.color.rgb = CLR_GREY

            img_table = report.add_table(rows=1, cols=4)
            img_table.alignment = WD_TABLE_ALIGNMENT.LEFT
            hdr = img_table.rows[0].cells
            hdr[0].text = 'Nr.'
            hdr[1].text = 'Bildname'
            hdr[2].text = 'Typ'
            hdr[3].text = 'Ähnlichkeit'
            for cell in hdr:
                set_cell_bg(cell, '1565C0')
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.bold = True
                        r.font.color.rgb = CLR_WHITE
                        r.font.size = Pt(9)

            img_type_labels = {
                'added': 'Hinzugefügt',
                'removed': 'Entfernt',
                'changed': 'Geändert',
            }
            img_type_colors = {
                'added': ('E8F5E9', CLR_INS),
                'removed': ('FFEBEE', CLR_DEL),
                'changed': ('FFF8E1', RGBColor(0xE6, 0x5C, 0x00)),
            }

            for idx, ic in enumerate(changed_images[:100], 1):
                row = img_table.add_row().cells
                row[0].text = str(idx)
                row[1].text = ic['name']
                row[2].text = img_type_labels.get(ic['type'], ic['type'])
                if ic['type'] == 'changed':
                    row[3].text = f"{ic['similarity_pct']}%"
                else:
                    row[3].text = '—'

                bg_hex, text_clr = img_type_colors.get(ic['type'], ('F5F5F5', CLR_GREY))
                for cell in row:
                    set_cell_bg(cell, bg_hex)
                    for p in cell.paragraphs:
                        for r in p.runs:
                            r.font.size = Pt(8)
                # Color the type column
                for p in row[2].paragraphs:
                    for r in p.runs:
                        r.font.color.rgb = text_clr
                        r.font.bold = True

            # Set column widths for image table
            for row in img_table.rows:
                row.cells[0].width = Cm(1)
                row.cells[1].width = Cm(6)
                row.cells[2].width = Cm(3)
                row.cells[3].width = Cm(3)

    except Exception:
        # Image comparison is best-effort; don't fail the report
        pass

    report_path = os.path.join(tmpdir, 'report.docx')
    report.save(report_path)
    return report_path


def _generate_xlsx_redline(filepath_a, filepath_b, tmpdir):
    """
    Generate an XLSX redline following Litera Compare conventions:
    - Separate colors for direct content changes vs indirect/formula changes
    - Cell content colored: deleted text in red, inserted text in blue
    - Cell background: light fill per change type
    - Inserted/deleted rows and columns detected and highlighted
    - Summary/Legend sheet with change statistics
    - Comments on changed cells showing old value
    - Formula change annotations
    """
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
    from openpyxl.comments import Comment
    import re

    wb_a_data = load_workbook(filepath_a, data_only=True)
    wb_a_formulas = load_workbook(filepath_a, data_only=False)
    wb_b = load_workbook(filepath_b, data_only=False)
    wb_b_data = load_workbook(filepath_b, data_only=True)

    # Color scheme (Litera-style)
    COLORS = {
        'direct_insert_fill': PatternFill(start_color='FFE8F5E9', end_color='FFE8F5E9', fill_type='solid'),
        'direct_delete_fill': PatternFill(start_color='FFFFEBEE', end_color='FFFFEBEE', fill_type='solid'),
        'direct_change_fill': PatternFill(start_color='FFFFF8E1', end_color='FFFFF8E1', fill_type='solid'),
        'indirect_fill': PatternFill(start_color='FFE3F2FD', end_color='FFE3F2FD', fill_type='solid'),
        'format_fill': PatternFill(start_color='FFF3E5F5', end_color='FFF3E5F5', fill_type='solid'),
        'inserted_row_fill': PatternFill(start_color='FFC8E6C9', end_color='FFC8E6C9', fill_type='solid'),
        'deleted_row_fill': PatternFill(start_color='FFFFCDD2', end_color='FFFFCDD2', fill_type='solid'),
    }
    FONTS = {
        'deleted': Font(color='C62828', strikethrough=True),
        'inserted': Font(color='1565C0', underline='single'),
        'changed_new': Font(color='1565C0'),
        'formula_change': Font(color='6A1B9A', italic=True),
        'header': Font(bold=True, size=11),
        'legend_label': Font(bold=True, size=10),
        'normal': Font(size=10),
    }
    change_border = Border(
        left=Side(style='thin', color='FFBDBDBD'),
        right=Side(style='thin', color='FFBDBDBD'),
        top=Side(style='thin', color='FFBDBDBD'),
        bottom=Side(style='thin', color='FFBDBDBD'),
    )

    # Collect all changes for summary
    all_changes = []

    # Build complete value + formula maps for version A
    data_a = {}   # coord -> display value
    formulas_a = {}  # coord -> formula string
    for sn in wb_a_data.sheetnames:
        ws_data = wb_a_data[sn]
        ws_form = wb_a_formulas[sn] if sn in wb_a_formulas.sheetnames else None
        for row in ws_data.iter_rows():
            for cell in row:
                if cell.value is not None:
                    key = f"{sn}!{cell.coordinate}"
                    data_a[key] = str(cell.value)
                    if ws_form:
                        fc = ws_form[cell.coordinate]
                        if fc.value is not None and str(fc.value).startswith('='):
                            formulas_a[key] = str(fc.value)

    # Detect inserted/deleted rows per sheet
    def get_row_keys(ws):
        """Get a list of row 'fingerprints' for row insertion/deletion detection."""
        rows = {}
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    r = cell.row
                    if r not in rows:
                        rows[r] = []
                    rows[r].append(str(cell.value))
        return {r: '|'.join(vals) for r, vals in rows.items()}

    # Process each sheet in version B
    for sn in wb_b.sheetnames:
        ws = wb_b[sn]

        # Detect inserted/deleted rows
        rows_a = get_row_keys(wb_a_data[sn]) if sn in wb_a_data.sheetnames else {}
        rows_b = get_row_keys(ws)

        fingerprints_a = set(rows_a.values())
        fingerprints_b = set(rows_b.values())

        inserted_rows = set()
        for r, fp in rows_b.items():
            if fp not in fingerprints_a and fp.strip('|'):
                inserted_rows.add(r)

        deleted_row_fps = {}
        for r, fp in rows_a.items():
            if fp not in fingerprints_b and fp.strip('|'):
                deleted_row_fps[r] = fp

        # Process cells
        for row in ws.iter_rows():
            for cell in row:
                key = f"{sn}!{cell.coordinate}"
                val_b_display = str(wb_b_data[sn][cell.coordinate].value) if wb_b_data[sn][cell.coordinate].value is not None else None
                val_b_formula = str(cell.value) if cell.value is not None and str(cell.value).startswith('=') else None
                val_b = val_b_display
                val_a = data_a.pop(key, None)
                formula_a = formulas_a.get(key)

                # Check if this is an inserted row
                if cell.row in inserted_rows and val_b is not None:
                    cell.fill = COLORS['inserted_row_fill']
                    cell.font = FONTS['inserted']
                    cell.border = change_border
                    all_changes.append({
                        'sheet': sn, 'cell': cell.coordinate,
                        'type': 'Eingefügte Zeile', 'new': val_b or '', 'old': ''
                    })
                    continue

                if val_a is None and val_b is not None:
                    # New cell (direct insert)
                    cell.fill = COLORS['direct_insert_fill']
                    cell.font = FONTS['inserted']
                    cell.border = change_border
                    all_changes.append({
                        'sheet': sn, 'cell': cell.coordinate,
                        'type': 'Neue Zelle', 'new': val_b, 'old': ''
                    })

                elif val_a is not None and val_b is not None and val_a != val_b:
                    # Content changed
                    # Check if formula changed
                    formula_b = val_b_formula
                    if formula_a and formula_b and formula_a != formula_b:
                        # Formula change (could be direct or indirect)
                        cell.fill = COLORS['direct_change_fill']
                        cell.font = FONTS['changed_new']
                        cell.border = change_border
                        cell.comment = Comment(
                            f"Alter Wert: {val_a}\nAlte Formel: {formula_a}\nNeue Formel: {formula_b}",
                            "MyCompare"
                        )
                        all_changes.append({
                            'sheet': sn, 'cell': cell.coordinate,
                            'type': 'Formeländerung',
                            'old': f"{val_a} ({formula_a})",
                            'new': f"{val_b} ({formula_b})"
                        })
                    elif formula_a and not formula_b:
                        # Formula removed
                        cell.fill = COLORS['direct_change_fill']
                        cell.font = FONTS['changed_new']
                        cell.border = change_border
                        cell.comment = Comment(
                            f"Alter Wert: {val_a}\nFormel entfernt: {formula_a}",
                            "MyCompare"
                        )
                        all_changes.append({
                            'sheet': sn, 'cell': cell.coordinate,
                            'type': 'Formel entfernt',
                            'old': f"{val_a} ({formula_a})", 'new': val_b
                        })
                    elif not formula_a and formula_b:
                        # Formula added
                        cell.fill = COLORS['direct_change_fill']
                        cell.font = FONTS['formula_change']
                        cell.border = change_border
                        cell.comment = Comment(
                            f"Alter Wert: {val_a}\nNeue Formel: {formula_b}",
                            "MyCompare"
                        )
                        all_changes.append({
                            'sheet': sn, 'cell': cell.coordinate,
                            'type': 'Formel hinzugefügt',
                            'old': val_a, 'new': f"{val_b} ({formula_b})"
                        })
                    else:
                        # Direct content change
                        cell.fill = COLORS['direct_change_fill']
                        cell.font = FONTS['changed_new']
                        cell.border = change_border
                        cell.comment = Comment(f"Alter Wert: {val_a}", "MyCompare")
                        all_changes.append({
                            'sheet': sn, 'cell': cell.coordinate,
                            'type': 'Inhalt geändert', 'old': val_a, 'new': val_b
                        })

                elif val_a is not None and val_b is None:
                    # Cell deleted (was in A, empty in B)
                    cell.fill = COLORS['direct_delete_fill']
                    cell.font = FONTS['deleted']
                    cell.value = val_a
                    cell.border = change_border
                    cell.comment = Comment("Zelle gelöscht", "MyCompare")
                    all_changes.append({
                        'sheet': sn, 'cell': cell.coordinate,
                        'type': 'Zelle gelöscht', 'old': val_a, 'new': ''
                    })

    # Handle cells that exist only in A (deleted from sheets still in B)
    remaining_by_sheet = {}
    for key, val in data_a.items():
        parts = key.split('!')
        sn = parts[0]
        coord = parts[1]
        if sn not in remaining_by_sheet:
            remaining_by_sheet[sn] = []
        remaining_by_sheet[sn].append((coord, val))

    for sn, cells in remaining_by_sheet.items():
        if sn in wb_b.sheetnames:
            ws = wb_b[sn]
            for coord, val in cells:
                try:
                    c = ws[coord]
                    if c.value is None:
                        c.value = val
                        c.fill = COLORS['direct_delete_fill']
                        c.font = FONTS['deleted']
                        c.border = change_border
                        c.comment = Comment("Zelle gelöscht", "MyCompare")
                        all_changes.append({
                            'sheet': sn, 'cell': coord,
                            'type': 'Zelle gelöscht', 'old': val, 'new': ''
                        })
                except Exception:
                    pass

    # Add deleted rows info for sheets in A not in B
    for sn in wb_a_data.sheetnames:
        if sn not in wb_b.sheetnames:
            all_changes.append({
                'sheet': sn, 'cell': '-',
                'type': 'Blatt gelöscht', 'old': sn, 'new': ''
            })

    # Add new sheets info
    for sn in wb_b.sheetnames:
        if sn not in wb_a_data.sheetnames:
            all_changes.append({
                'sheet': sn, 'cell': '-',
                'type': 'Neues Blatt', 'old': '', 'new': sn
            })

    # ─── Create Summary & Legend Sheet ───
    ws_summary = wb_b.create_sheet('Änderungsübersicht', 0)  # Insert as first sheet

    # Title
    ws_summary.merge_cells('A1:F1')
    title_cell = ws_summary['A1']
    title_cell.value = 'Änderungsübersicht — MyCompare Redline'
    title_cell.font = Font(bold=True, size=14, color='1565C0')
    title_cell.alignment = Alignment(horizontal='center')

    # Legend
    ws_summary['A3'] = 'Legende:'
    ws_summary['A3'].font = FONTS['legend_label']

    legend_items = [
        ('Neue Zelle / Eingefügt', COLORS['direct_insert_fill'], FONTS['inserted']),
        ('Gelöscht', COLORS['direct_delete_fill'], FONTS['deleted']),
        ('Inhalt geändert', COLORS['direct_change_fill'], FONTS['changed_new']),
        ('Formeländerung', COLORS['direct_change_fill'], FONTS['formula_change']),
        ('Eingefügte Zeile', COLORS['inserted_row_fill'], FONTS['inserted']),
        ('Indirekte Änderung', COLORS['indirect_fill'], FONTS['normal']),
    ]
    for i, (label, fill, font) in enumerate(legend_items):
        row = 4 + i
        c = ws_summary.cell(row, 1, '  Beispiel  ')
        c.fill = fill
        c.font = font
        c.border = change_border
        ws_summary.cell(row, 2, f'  = {label}').font = FONTS['normal']

    # Statistics
    stats_row = 4 + len(legend_items) + 1
    ws_summary.cell(stats_row, 1, 'Statistik:').font = FONTS['legend_label']

    from collections import Counter

    # ── Table-level changes for report ──
    tables_a = doc_a.tables
    tables_b = doc_b.tables
    num_tables_report = max(len(tables_a), len(tables_b))

    for tbl_idx in range(num_tables_report):
        tbl_a_rep = tables_a[tbl_idx] if tbl_idx < len(tables_a) else None
        tbl_b_rep = tables_b[tbl_idx] if tbl_idx < len(tables_b) else None
        tbl_label = f'Tabelle {tbl_idx + 1}'

        if tbl_a_rep is None and tbl_b_rep is not None:
            record_change('Tabellenänderung', '', f'{tbl_label}: Gesamte Tabelle eingefügt')
        elif tbl_b_rep is None and tbl_a_rep is not None:
            record_change('Tabellenänderung', f'{tbl_label}: Gesamte Tabelle gelöscht', '')
        else:
            # Compare row-by-row, cell-by-cell
            num_rows_a_rep = len(tbl_a_rep.rows)
            num_rows_b_rep = len(tbl_b_rep.rows)

            def _row_texts_report(table, n_rows):
                """Get concatenated cell text per row."""
                result = []
                for ri in range(n_rows):
                    cells_text = []
                    for ci in range(len(table.rows[ri].cells)):
                        cells_text.append(table.rows[ri].cells[ci].text or '')
                    result.append('\t'.join(cells_text))
                return result

            rtexts_a_rep = _row_texts_report(tbl_a_rep, num_rows_a_rep)
            rtexts_b_rep = _row_texts_report(tbl_b_rep, num_rows_b_rep)

            row_sm_rep = difflib.SequenceMatcher(None, rtexts_a_rep, rtexts_b_rep, autojunk=False)
            for rtag, ri1, ri2, rj1, rj2 in row_sm_rep.get_opcodes():
                if rtag == 'equal':
                    for offset in range(rj2 - rj1):
                        a_ri = ri1 + offset
                        b_ri = rj1 + offset
                        row_a_rep = tbl_a_rep.rows[a_ri]
                        row_b_rep = tbl_b_rep.rows[b_ri]
                        num_cells = min(len(row_a_rep.cells), len(row_b_rep.cells))
                        for ci in range(num_cells):
                            text_a = row_a_rep.cells[ci].text or ''
                            text_b = row_b_rep.cells[ci].text or ''
                            if text_a != text_b:
                                cell_ref = f'{tbl_label}, Zeile {a_ri + 1}, Zelle {ci + 1}'
                                record_change('Tabellenänderung',
                                              f'{cell_ref}: {text_a[:100]}',
                                              f'{cell_ref}: {text_b[:100]}')
                elif rtag == 'replace':
                    for idx in range(ri1, ri2):
                        record_change('Tabellenänderung',
                                      f'{tbl_label}, Zeile {idx + 1}: {rtexts_a_rep[idx][:100]}', '')
                    for idx in range(rj1, rj2):
                        record_change('Tabellenänderung',
                                      '', f'{tbl_label}, Zeile {idx + 1}: {rtexts_b_rep[idx][:100]}')
                elif rtag == 'delete':
                    for idx in range(ri1, ri2):
                        record_change('Tabellenänderung',
                                      f'{tbl_label}, Zeile {idx + 1}: {rtexts_a_rep[idx][:100]}', '')
                elif rtag == 'insert':
                    for idx in range(rj1, rj2):
                        record_change('Tabellenänderung',
                                      '', f'{tbl_label}, Zeile {idx + 1}: {rtexts_b_rep[idx][:100]}')

    type_counts = Counter(c['type'] for c in all_changes)
    for i, (ctype, count) in enumerate(type_counts.most_common()):
        ws_summary.cell(stats_row + 1 + i, 1, ctype).font = FONTS['normal']
        ws_summary.cell(stats_row + 1 + i, 2, count).font = Font(bold=True, size=10)

    total_row = stats_row + 1 + len(type_counts)
    ws_summary.cell(total_row + 1, 1, 'Gesamt:').font = FONTS['legend_label']
    ws_summary.cell(total_row + 1, 2, len(all_changes)).font = Font(bold=True, size=12, color='1565C0')

    # Change detail table
    detail_row = total_row + 3
    ws_summary.cell(detail_row, 1, 'Alle Änderungen:').font = FONTS['legend_label']
    headers = ['Blatt', 'Zelle', 'Typ', 'Alter Wert', 'Neuer Wert']
    for col, h in enumerate(headers, 1):
        c = ws_summary.cell(detail_row + 1, col, h)
        c.font = Font(bold=True, size=10, color='FFFFFF')
        c.fill = PatternFill(start_color='FF1565C0', end_color='FF1565C0', fill_type='solid')
        c.alignment = Alignment(horizontal='center')

    for i, change in enumerate(all_changes[:500]):  # Limit to 500 rows
        r = detail_row + 2 + i
        ws_summary.cell(r, 1, change['sheet'])
        ws_summary.cell(r, 2, change['cell'])
        ws_summary.cell(r, 3, change['type'])
        old_cell = ws_summary.cell(r, 4, change['old'][:100] if change['old'] else '')
        old_cell.font = FONTS['deleted'] if change['old'] else FONTS['normal']
        new_cell = ws_summary.cell(r, 5, change['new'][:100] if change['new'] else '')
        new_cell.font = FONTS['inserted'] if change['new'] else FONTS['normal']

    # Auto-width columns
    for col_letter in ['A', 'B', 'C', 'D', 'E', 'F']:
        ws_summary.column_dimensions[col_letter].width = 20

    if len(all_changes) > 500:
        r = detail_row + 502
        ws_summary.cell(r, 1, f'... und {len(all_changes) - 500} weitere Änderungen').font = Font(italic=True, color='999999')

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
    Export changes. format=original copies version B, format=pdf generates a redline PDF.
    Query param: format=original|pdf
    """
    import tempfile
    import shutil

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

        # For PDF format: generate a redline PDF directly
        if output_format == 'pdf':
            tmpdir = tempfile.mkdtemp()
            try:
                out_path = _generate_redline_pdf(ver_a.filepath, ver_b.filepath, doc.file_type, tmpdir)
                dl_name = f"{doc.name}_Redline_V{version_a}_vs_V{version_b}.pdf"
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

        # For original format: export version B as-is
        tmpdir = tempfile.mkdtemp()
        try:
            ext = {'docx': '.docx', 'xlsx': '.xlsx', 'pptx': '.pptx', 'pdf': '.pdf',
                   'rtf': '.rtf', 'txt': '.txt'}.get(doc.file_type, '.bin')
            out_path = os.path.join(tmpdir, f'export{ext}')
            shutil.copy2(ver_b.filepath, out_path)
            dl_name = f"{doc.name}_V{version_b}{ext}"
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
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


def _generate_redline_pdf(filepath_a, filepath_b, file_type, tmpdir, pdfa=False):
    """
    Generate a professional PDF redline with Litera Compare-style formatting:
    - Title page with legend, statistics table, numbered change list
    - Full document text with inline change markup (red strikethrough / blue underline)
    - Word-level granularity for replacements
    - Move detection
    Works for all file types. Supports PDF/A output for long-term archiving.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, black
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, PageBreak)
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from html import escape
    from collections import Counter
    from datetime import datetime
    import difflib
    import re

    # Extract text from both versions
    struct_a, text_a = extract(filepath_a, file_type)
    struct_b, text_b = extract(filepath_b, file_type)

    out_path = os.path.join(tmpdir, 'redline.pdf')
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('RTitle', parent=styles['Title'], fontSize=18,
                                  spaceAfter=4*mm, textColor=HexColor('#1565C0'))
    subtitle_style = ParagraphStyle('RSub', parent=styles['Normal'], fontSize=11,
                                     spaceAfter=2*mm, textColor=HexColor('#666666'),
                                     alignment=1)
    heading_style = ParagraphStyle('RH', parent=styles['Heading2'], fontSize=14,
                                    textColor=HexColor('#1F3864'), spaceBefore=6*mm,
                                    spaceAfter=3*mm)
    body_style = ParagraphStyle('RBody', parent=styles['Normal'],
                                 fontSize=10, leading=14, fontName='Helvetica')
    small_style = ParagraphStyle('RSmall', parent=styles['Normal'],
                                  fontSize=8, leading=10, textColor=colors.grey)
    legend_label = ParagraphStyle('RLbl', parent=styles['Normal'],
                                   fontSize=9, leading=12, fontName='Helvetica-Bold')

    # ── Compute diff and collect changes ──
    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()

    # Move detection
    sm_pre = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    deleted_lines = {}
    inserted_lines = {}
    for tag, i1, i2, j1, j2 in sm_pre.get_opcodes():
        if tag == 'delete':
            for idx in range(i1, i2):
                txt = lines_a[idx].strip()
                if txt and len(txt) > 15:
                    deleted_lines.setdefault(txt, []).append(idx)
        elif tag == 'insert':
            for idx in range(j1, j2):
                txt = lines_b[idx].strip()
                if txt and len(txt) > 15:
                    inserted_lines.setdefault(txt, []).append(idx)

    moved_from = set()
    moved_to = set()
    for txt in deleted_lines:
        if txt in inserted_lines:
            for a_idx, b_idx in zip(deleted_lines[txt], inserted_lines[txt]):
                moved_from.add(a_idx)
                moved_to.add(b_idx)

    # Collect all changes
    all_changes = []
    change_num = [0]

    def record(ctype, old='', new=''):
        change_num[0] += 1
        all_changes.append({
            'num': change_num[0], 'type': ctype,
            'old': (old or '')[:100], 'new': (new or '')[:100]
        })

    sm = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    opcodes = sm.get_opcodes()

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'replace':
            for idx in range(max(i2 - i1, j2 - j1)):
                old = lines_a[i1 + idx] if (i1 + idx) < i2 else ''
                new = lines_b[j1 + idx] if (j1 + idx) < j2 else ''
                if old and new:
                    record('Ersetzung', old, new)
                elif old:
                    record('Löschung', old)
                else:
                    record('Einfügung', new=new)
        elif tag == 'delete':
            for idx in range(i1, i2):
                if idx in moved_from:
                    record('Verschoben (Quelle)', lines_a[idx])
                else:
                    record('Löschung', lines_a[idx])
        elif tag == 'insert':
            for idx in range(j1, j2):
                if idx in moved_to:
                    record('Verschoben (Ziel)', new=lines_b[idx])
                else:
                    record('Einfügung', new=lines_b[idx])

    type_counts = Counter(c['type'] for c in all_changes)
    total_changes = len(all_changes)

    # ── Build PDF story ──
    story = []

    # ─── Page 1: Title & Legend ───
    story.append(Paragraph("Änderungsbericht", title_style))
    story.append(Paragraph("MyCompare — Dokumentenvergleich", subtitle_style))
    story.append(Paragraph(
        f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}", subtitle_style))
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph("Legende", heading_style))
    legend_data = [
        ['Darstellung', 'Bedeutung'],
        [Paragraph('<font color="red"><strike>Rot durchgestrichen</strike></font>', body_style),
         'Gelöschter Text'],
        [Paragraph('<font color="blue"><u>Blau unterstrichen</u></font>', body_style),
         'Eingefügter Text'],
        [Paragraph('<font color="#6A1B9A">Lila</font>', body_style),
         'Verschobener Text'],
        ['Schwarz', 'Unveränderter Text'],
    ]
    legend_tbl = Table(legend_data, colWidths=[60*mm, 90*mm])
    legend_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1565C0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BDBDBD')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(legend_tbl)
    story.append(Spacer(1, 6*mm))

    # ─── Statistics ───
    story.append(Paragraph("Änderungsstatistik", heading_style))
    type_colors_map = {
        'Einfügung': '#E8F5E9', 'Löschung': '#FFEBEE', 'Ersetzung': '#FFF8E1',
        'Verschoben (Quelle)': '#F3E5F5', 'Verschoben (Ziel)': '#F3E5F5',
    }
    stats_data = [['Änderungstyp', 'Anzahl']]
    stats_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1565C0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BDBDBD')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]
    row_idx = 1
    for ctype, count in type_counts.most_common():
        stats_data.append([ctype, str(count)])
        bg = type_colors_map.get(ctype, '#F5F5F5')
        stats_styles.append(('BACKGROUND', (0, row_idx), (-1, row_idx), HexColor(bg)))
        row_idx += 1
    stats_data.append(['Gesamt', str(total_changes)])
    stats_styles.append(('BACKGROUND', (0, row_idx), (-1, row_idx), HexColor('#E3F2FD')))
    stats_styles.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))

    stats_tbl = Table(stats_data, colWidths=[80*mm, 30*mm])
    stats_tbl.setStyle(TableStyle(stats_styles))
    story.append(stats_tbl)

    # ─── Change List ───
    story.append(PageBreak())
    story.append(Paragraph("Änderungsliste", heading_style))

    changes_data = [['Nr.', 'Typ', 'Alter Text', 'Neuer Text']]
    changes_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1565C0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BDBDBD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]
    for i, change in enumerate(all_changes[:150]):
        old_d = escape(change['old']) if change['old'] else '—'
        new_d = escape(change['new']) if change['new'] else '—'
        changes_data.append([
            str(change['num']), change['type'],
            Paragraph(f'<font size="7">{old_d}</font>', body_style),
            Paragraph(f'<font size="7">{new_d}</font>', body_style),
        ])
        bg = type_colors_map.get(change['type'], '#F5F5F5')
        changes_styles.append(('BACKGROUND', (0, i+1), (-1, i+1), HexColor(bg)))

    if total_changes > 150:
        changes_data.append(['', f'... und {total_changes - 150} weitere', '', ''])

    changes_tbl = Table(changes_data, colWidths=[12*mm, 30*mm, 60*mm, 60*mm])
    changes_tbl.setStyle(TableStyle(changes_styles))
    story.append(changes_tbl)

    # ─── Page: Redline Document ───
    story.append(PageBreak())
    story.append(Paragraph("Redline-Dokument", heading_style))

    # Legend reminder
    legend_html = (
        '<font color="red"><strike>Rot</strike></font> = gelöscht &nbsp; '
        '<font color="blue"><u>Blau</u></font> = eingefügt &nbsp; '
        '<font color="#6A1B9A">Lila</font> = verschoben &nbsp; '
        'Schwarz = unverändert'
    )
    story.append(Paragraph(legend_html, small_style))
    story.append(Spacer(1, 4*mm))

    # Render full document with inline changes
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            for idx in range(i1, i2):
                safe = escape(lines_a[idx]) or '&nbsp;'
                story.append(Paragraph(safe, body_style))

        elif tag == 'replace':
            for idx in range(max(i2 - i1, j2 - j1)):
                old_line = lines_a[i1 + idx] if (i1 + idx) < i2 else ''
                new_line = lines_b[j1 + idx] if (j1 + idx) < j2 else ''

                if old_line and new_line:
                    words_a = re.findall(r'\S+|\s+', old_line)
                    words_b = re.findall(r'\S+|\s+', new_line)
                    wsm = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)
                    parts = []
                    for wtag, wi1, wi2, wj1, wj2 in wsm.get_opcodes():
                        if wtag == 'equal':
                            parts.append(escape(''.join(words_b[wj1:wj2])))
                        elif wtag == 'replace':
                            parts.append(f'<font color="red"><strike>{escape("".join(words_a[wi1:wi2]))}</strike></font>')
                            parts.append(f'<font color="blue"><u>{escape("".join(words_b[wj1:wj2]))}</u></font>')
                        elif wtag == 'delete':
                            parts.append(f'<font color="red"><strike>{escape("".join(words_a[wi1:wi2]))}</strike></font>')
                        elif wtag == 'insert':
                            parts.append(f'<font color="blue"><u>{escape("".join(words_b[wj1:wj2]))}</u></font>')
                    story.append(Paragraph(''.join(parts) or '&nbsp;', body_style))
                elif old_line:
                    safe = escape(old_line)
                    story.append(Paragraph(f'<font color="red"><strike>{safe}</strike></font>', body_style))
                elif new_line:
                    safe = escape(new_line)
                    story.append(Paragraph(f'<font color="blue"><u>{safe}</u></font>', body_style))

        elif tag == 'delete':
            for idx in range(i1, i2):
                safe = escape(lines_a[idx])
                if idx in moved_from:
                    story.append(Paragraph(
                        f'<font color="#6A1B9A"><strike>{safe}</strike> [verschoben]</font>', body_style))
                else:
                    story.append(Paragraph(
                        f'<font color="red"><strike>{safe}</strike></font>', body_style))

        elif tag == 'insert':
            for idx in range(j1, j2):
                safe = escape(lines_b[idx])
                if idx in moved_to:
                    story.append(Paragraph(
                        f'<font color="#6A1B9A"><u>{safe}</u> [hierhin verschoben]</font>', body_style))
                else:
                    story.append(Paragraph(
                        f'<font color="blue"><u>{safe}</u></font>', body_style))

    if total_changes == 0:
        story.append(Paragraph("Keine Änderungen erkannt.", body_style))

    doc.build(story)

    # Convert to PDF/A if requested
    if pdfa:
        try:
            _apply_pdfa_metadata(out_path)
        except Exception:
            pass  # Fall back to regular PDF if PDF/A conversion fails

    return out_path


def _apply_pdfa_metadata(pdf_path):
    """Add PDF/A-1b compliance metadata (XMP and output intent) to an existing PDF."""
    from PyPDF2 import PdfReader, PdfWriter
    from PyPDF2.generic import (
        DecodedStreamObject, ArrayObject, DictionaryObject,
        NameObject, NumberObject, TextStringObject,
    )
    from datetime import datetime

    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # Add XMP metadata for PDF/A-1b
    now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    xmp = f'''<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about=""
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
  xmlns:xmp="http://ns.adobe.com/xap/1.0/">
  <pdfaid:part>1</pdfaid:part>
  <pdfaid:conformance>B</pdfaid:conformance>
  <dc:title><rdf:Alt><rdf:li xml:lang="x-default">MyCompare Redline</rdf:li></rdf:Alt></dc:title>
  <dc:creator><rdf:Seq><rdf:li>MyCompare</rdf:li></rdf:Seq></dc:creator>
  <xmp:CreateDate>{now}</xmp:CreateDate>
  <xmp:ModifyDate>{now}</xmp:ModifyDate>
</rdf:Description>
</rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''

    metadata_stream = DecodedStreamObject()
    metadata_stream.set_data(xmp.encode('utf-8'))
    metadata_stream[NameObject('/Type')] = NameObject('/Metadata')
    metadata_stream[NameObject('/Subtype')] = NameObject('/XML')
    metadata_ref = writer._add_object(metadata_stream)
    writer._root_object[NameObject('/Metadata')] = metadata_ref

    # Write
    with open(pdf_path, 'wb') as f:
        writer.write(f)


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
# P2.12 – Export only changed pages/sections
# ═══════════════════════════════════════════════════════════════════════════════

def _find_changed_pages_pdf(filepath_a, filepath_b):
    """
    Extract text per page from both PDFs and return a list of 1-based page
    numbers (from version B) that have differences.
    """
    import pdfplumber

    def pdf_pages_text(path):
        pages = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or '')
        return pages

    pages_a = pdf_pages_text(filepath_a)
    pages_b = pdf_pages_text(filepath_b)

    changed = []
    max_pages = max(len(pages_a), len(pages_b))
    for i in range(max_pages):
        text_a = pages_a[i] if i < len(pages_a) else ''
        text_b = pages_b[i] if i < len(pages_b) else ''
        if text_a != text_b:
            changed.append(i + 1)

    return changed, len(pages_b)


@api.route('/export-changed-pages-only/<int:doc_id>/<int:version_a>/<int:version_b>', methods=['GET'])
def export_changed_pages_only(doc_id, version_a, version_b):
    """
    Export only the pages/sections that contain changes between two versions.
    Query param: format=pdf|original (default: original)
    - PDF files: extract only changed pages into a new PDF
    - DOCX files: extract only changed paragraphs (with 1 paragraph context)
    - XLSX files: export only sheets that have changes
    """
    import tempfile
    import shutil

    output_format = request.args.get('format', 'original')
    if output_format not in ('original', 'pdf'):
        return jsonify({'error': 'Format muss "original" oder "pdf" sein'}), 400

    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Dokument nicht gefunden'}), 404

        ver_a = session.query(Version).filter_by(
            document_id=doc_id, version_number=version_a).first()
        ver_b = session.query(Version).filter_by(
            document_id=doc_id, version_number=version_b).first()
        if not ver_a or not ver_b:
            return jsonify({'error': 'Version nicht gefunden'}), 404

        tmpdir = tempfile.mkdtemp()
        try:
            out_path = None

            if doc.file_type == 'pdf':
                out_path = _export_changed_pages_pdf(
                    ver_a.filepath, ver_b.filepath, tmpdir, output_format)

            elif doc.file_type == 'docx':
                out_path = _export_changed_paragraphs_docx(
                    ver_a.filepath, ver_b.filepath, tmpdir, output_format)

            elif doc.file_type == 'xlsx':
                out_path = _export_changed_sheets_xlsx(
                    ver_a.filepath, ver_b.filepath, tmpdir, output_format)

            else:
                return jsonify({
                    'error': 'Export nur geänderter Seiten wird für diesen '
                             'Dateityp nicht unterstützt'
                }), 400

            if not out_path or not os.path.exists(out_path):
                return jsonify({
                    'error': 'Keine Änderungen gefunden oder Export fehlgeschlagen'
                }), 404

            ext = os.path.splitext(out_path)[1]
            dl_name = (f"{doc.name}_NurAenderungen"
                       f"_V{version_a}_vs_V{version_b}{ext}")
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
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


def _export_changed_pages_pdf(filepath_a, filepath_b, tmpdir, output_format):
    """Extract only changed pages from a PDF into a new PDF."""
    from PyPDF2 import PdfReader, PdfWriter

    changed_pages, total_pages = _find_changed_pages_pdf(filepath_a, filepath_b)
    if not changed_pages:
        return None

    reader_b = PdfReader(filepath_b)
    writer = PdfWriter()

    for page_num in changed_pages:
        idx = page_num - 1
        if idx < len(reader_b.pages):
            writer.add_page(reader_b.pages[idx])

    out_path = os.path.join(tmpdir, 'changed_pages.pdf')
    with open(out_path, 'wb') as f:
        writer.write(f)
    return out_path


def _export_changed_paragraphs_docx(filepath_a, filepath_b, tmpdir,
                                     output_format):
    """
    Export changes between two DOCX versions.
    - Word format: Returns the full redline DOCX with tracked changes
      (complete pages, not just extracted paragraphs).
    - PDF format: Generates a reportlab-based redline PDF with change markup
      (works on all platforms without LibreOffice).
    """
    if output_format == 'pdf':
        # Use reportlab-based PDF generation (no LibreOffice needed)
        # Determine file_type from the file extension
        ext = os.path.splitext(filepath_b)[1].lower().lstrip('.')
        file_type = ext if ext in ('docx', 'xlsx', 'pptx', 'pdf', 'txt') else 'docx'
        pdf_path = _generate_redline_pdf(filepath_a, filepath_b, file_type, tmpdir)
        if pdf_path and os.path.exists(pdf_path):
            return pdf_path
        return None

    # Word format: return the full redline DOCX with all tracked changes
    redline_path = _generate_docx_redline(filepath_a, filepath_b, tmpdir)
    return redline_path


def _convert_docx_to_pdf(docx_path, tmpdir):
    """Try to convert a DOCX to PDF using LibreOffice, return path or None."""
    import subprocess
    try:
        subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'pdf',
             '--outdir', tmpdir, docx_path],
            capture_output=True, timeout=60,
        )
        base = os.path.splitext(os.path.basename(docx_path))[0]
        pdf_path = os.path.join(tmpdir, f'{base}.pdf')
        if os.path.exists(pdf_path):
            return pdf_path
    except Exception:
        pass
    return None


def _export_changed_sheets_xlsx(filepath_a, filepath_b, tmpdir,
                                 output_format):
    """Export only sheets that have changes between two XLSX files."""
    from openpyxl import load_workbook, Workbook
    import copy as copy_mod

    wb_a = load_workbook(filepath_a, data_only=True)
    wb_b = load_workbook(filepath_b, data_only=True)

    sheets_a = {ws.title: ws for ws in wb_a.worksheets}
    sheets_b = {ws.title: ws for ws in wb_b.worksheets}

    changed_sheets = []

    for name, ws_b in sheets_b.items():
        ws_a = sheets_a.get(name)
        if ws_a is None:
            changed_sheets.append(name)
            continue
        # Compare cell values
        has_diff = False
        max_row = max(ws_a.max_row or 1, ws_b.max_row or 1)
        max_col = max(ws_a.max_column or 1, ws_b.max_column or 1)
        for row in range(1, max_row + 1):
            for col in range(1, max_col + 1):
                if (ws_a.cell(row=row, column=col).value
                        != ws_b.cell(row=row, column=col).value):
                    has_diff = True
                    break
            if has_diff:
                break
        if has_diff:
            changed_sheets.append(name)

    # Deleted sheets
    for name in sheets_a:
        if name not in sheets_b:
            changed_sheets.append(f'{name} (gelöscht)')

    if not changed_sheets:
        return None

    out_wb = Workbook()
    default_sheet = out_wb.active
    first = True

    for name in changed_sheets:
        if name.endswith(' (gelöscht)'):
            ws_out = out_wb.create_sheet(title=name[:31])
            ws_out.cell(row=1, column=1,
                        value='Dieses Blatt wurde in der neuen Version gelöscht.')
            if first:
                out_wb.remove(default_sheet)
                first = False
            continue

        ws_b = sheets_b[name]
        ws_out = out_wb.create_sheet(title=name[:31])
        if first:
            out_wb.remove(default_sheet)
            first = False

        for row in ws_b.iter_rows():
            for cell in row:
                new_cell = ws_out.cell(
                    row=cell.row, column=cell.column, value=cell.value)
                if cell.has_style:
                    new_cell.font = copy_mod.copy(cell.font)
                    new_cell.fill = copy_mod.copy(cell.fill)
                    new_cell.border = copy_mod.copy(cell.border)
                    new_cell.number_format = cell.number_format
                    new_cell.alignment = copy_mod.copy(cell.alignment)

    out_path = os.path.join(tmpdir, 'changed_sheets.xlsx')
    out_wb.save(out_path)

    if output_format == 'pdf':
        pdf_path = _convert_docx_to_pdf(out_path, tmpdir)
        if pdf_path:
            return pdf_path

    return out_path


# ── Rendering Sets CRUD ──

@api.route('/rendering-sets', methods=['GET'])
def list_rendering_sets():
    """List all rendering sets (comparison profiles)."""
    session = SessionLocal()
    try:
        sets = session.query(RenderingSet).order_by(
            RenderingSet.is_default.desc(), RenderingSet.name).all()
        return jsonify([rs.to_dict() for rs in sets])
    finally:
        session.close()


@api.route('/rendering-sets', methods=['POST'])
def create_rendering_set():
    """Create a new rendering set."""
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Name erforderlich'}), 400

    session = SessionLocal()
    try:
        import json
        rs = RenderingSet(
            name=data['name'],
            description=data.get('description', ''),
            settings_json=json.dumps(data.get('settings', {}), ensure_ascii=False),
        )
        session.add(rs)
        session.commit()
        session.refresh(rs)
        return jsonify(rs.to_dict()), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@api.route('/rendering-sets/<int:rs_id>', methods=['GET'])
def get_rendering_set(rs_id):
    """Get a single rendering set."""
    session = SessionLocal()
    try:
        rs = session.query(RenderingSet).get(rs_id)
        if not rs:
            return jsonify({'error': 'Nicht gefunden'}), 404
        return jsonify(rs.to_dict())
    finally:
        session.close()


@api.route('/rendering-sets/<int:rs_id>', methods=['PUT'])
def update_rendering_set(rs_id):
    """Update a rendering set."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body erforderlich'}), 400

    session = SessionLocal()
    try:
        import json
        rs = session.query(RenderingSet).get(rs_id)
        if not rs:
            return jsonify({'error': 'Nicht gefunden'}), 404

        if 'name' in data:
            rs.name = data['name']
        if 'description' in data:
            rs.description = data['description']
        if 'settings' in data:
            rs.settings_json = json.dumps(data['settings'], ensure_ascii=False)
        if 'is_default' in data and data['is_default']:
            for other in session.query(RenderingSet).filter(
                    RenderingSet.id != rs_id).all():
                other.is_default = False
            rs.is_default = True

        session.commit()
        session.refresh(rs)
        return jsonify(rs.to_dict())
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@api.route('/rendering-sets/<int:rs_id>', methods=['DELETE'])
def delete_rendering_set(rs_id):
    """Delete a rendering set."""
    session = SessionLocal()
    try:
        rs = session.query(RenderingSet).get(rs_id)
        if not rs:
            return jsonify({'error': 'Nicht gefunden'}), 404
        if rs.is_default:
            return jsonify({'error': 'Standard-Profil kann nicht gelöscht werden'}), 400
        session.delete(rs)
        session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# ── 1:Many Comparison ──

@api.route('/multi-compare', methods=['POST'])
def multi_compare():
    """
    Compare one original document against up to 5 modified versions.
    Expects: file_original + file_modified_1 ... file_modified_N (up to 5)
    Returns: individual diff results for each pair + merged summary.
    """
    if 'file_original' not in request.files:
        return jsonify({'error': 'Bitte eine Originaldatei hochladen (file_original)'}), 400

    file_original = request.files['file_original']
    if not file_original.filename:
        return jsonify({'error': 'Originaldatei hat keinen Namen'}), 400

    type_orig = get_file_type(file_original.filename)
    if not type_orig:
        return jsonify({
            'error': 'Nicht unterstützter Dateityp. Erlaubt: DOCX, XLSX, PPTX, PDF, RTF, TXT, HTML'
        }), 400

    # Collect modified files
    modified_files = []
    for i in range(1, 6):
        key = f'file_modified_{i}'
        if key in request.files:
            f = request.files[key]
            if f.filename:
                ft = get_file_type(f.filename)
                if ft != type_orig:
                    return jsonify({
                        'error': f'Datei {f.filename}: Typ {ft} passt nicht zum Original ({type_orig})'
                    }), 400
                modified_files.append(f)

    if not modified_files:
        return jsonify({'error': 'Mindestens eine modifizierte Datei erforderlich'}), 400

    if len(modified_files) > 5:
        return jsonify({'error': 'Maximal 5 modifizierte Versionen erlaubt'}), 400

    import tempfile
    import shutil
    tmpdir = tempfile.mkdtemp()

    try:
        # Save original
        orig_path = os.path.join(tmpdir, secure_filename(file_original.filename) or 'original')
        file_original.save(orig_path)
        struct_orig, text_orig = extract(orig_path, type_orig)

        options = {
            'ignore_whitespace': request.form.get('ignore_whitespace') == '1',
            'ignore_case': request.form.get('ignore_case') == '1',
            'ignore_headers_footers': request.form.get('ignore_headers_footers') == '1',
        }

        comparisons = []
        merged_changes = []
        total_stats = {
            'total_changes': 0,
            'additions': 0,
            'deletions': 0,
            'replacements': 0,
            'moves': 0,
            'formatting': 0,
        }

        for idx, mod_file in enumerate(modified_files):
            mod_name = secure_filename(mod_file.filename) or f'modified_{idx}'
            mod_path = os.path.join(tmpdir, f'{idx}_{mod_name}')
            mod_file.save(mod_path)

            struct_mod, text_mod = extract(mod_path, type_orig)
            result = compute_diff(
                struct_orig, text_orig, struct_mod, text_mod, type_orig, options)

            summary = result.get('summary', {})
            total_stats['total_changes'] += summary.get('total_changes', 0)
            total_stats['additions'] += summary.get('additions', 0)
            total_stats['deletions'] += summary.get('deletions', 0)
            total_stats['replacements'] += summary.get('replacements', 0)
            total_stats['moves'] += summary.get('move_count', 0)
            total_stats['formatting'] += summary.get('formatting_count', 0)

            for ch in result.get('structural_changes', []):
                ch['source_file'] = mod_file.filename
                ch['source_index'] = idx
                merged_changes.append(ch)

            comparisons.append({
                'filename': mod_file.filename,
                'index': idx,
                'summary': summary,
                'structural_changes': result.get('structural_changes', []),
                'unified_lines': result.get('unified_lines', []),
                'verification': result.get('verification'),
            })

        return jsonify({
            'comparisons': comparisons,
            'merged_changes': merged_changes,
            'total_stats': total_stats,
            'file_count': len(modified_files),
            'original_filename': file_original.filename,
            'file_type': type_orig,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        import threading

        def cleanup_multi():
            import time
            time.sleep(10)
            shutil.rmtree(tmpdir, ignore_errors=True)
        threading.Thread(target=cleanup_multi, daemon=True).start()


# ─── AI Analysis (Ollama) ───────────────────────────────────────────────

@api.route('/ai/status', methods=['GET'])
def ai_status():
    """Check AI providers status (Ollama + Claude)."""
    providers = get_providers_status()
    # Backwards-compatible: top-level 'available' and 'models' for Ollama
    return jsonify({
        'available': providers['ollama']['available'],
        'models': providers['ollama']['models'],
        'providers': providers,
    })


@api.route('/ai/api-key', methods=['POST'])
def ai_set_api_key():
    """Set the Anthropic API key."""
    data = request.get_json() or {}
    key = data.get('api_key', '').strip()
    if not key:
        return jsonify({'error': 'Kein API-Key angegeben'}), 400
    set_api_key(key)
    return jsonify({'status': 'ok', 'message': 'API-Key gespeichert'})


@api.route('/ai/api-key', methods=['GET'])
def ai_get_api_key():
    """Check if an API key is configured (don't return the actual key)."""
    key = get_api_key()
    return jsonify({
        'has_key': bool(key),
        'key_preview': f"{key[:10]}...{key[-4:]}" if key and len(key) > 14 else '',
    })


@api.route('/ai/analyze/<int:doc_id>/<int:version_a>/<int:version_b>',
           methods=['POST'])
def ai_analyze(doc_id, version_a, version_b):
    """
    Generate an AI-powered issue list from the changes between two versions.
    Requires JSON body: { "client_party": "Käufer" }
    Optional: { "model": "...", "document_context": "...", "provider": "ollama"|"claude" }
    """
    data = request.get_json() or {}
    client_party = data.get('client_party', '').strip()
    provider = data.get('provider', 'ollama')
    if not client_party:
        return jsonify({
            'error': 'Bitte geben Sie an, wen Sie vertreten (client_party).'
        }), 400

    model = data.get('model')
    document_context = data.get('document_context', '')
    client_version = data.get('client_version', 'a')

    session = SessionLocal()
    try:
        doc = session.query(Document).get(doc_id)
        if not doc:
            return jsonify({'error': 'Dokument nicht gefunden'}), 404

        ver_a = session.query(Version).filter_by(
            document_id=doc_id, version_number=version_a).first()
        ver_b = session.query(Version).filter_by(
            document_id=doc_id, version_number=version_b).first()
        if not ver_a or not ver_b:
            return jsonify({'error': 'Version nicht gefunden'}), 404

        # Extract text and compute diff to get changes
        struct_a, text_a = extract(ver_a.filepath, doc.file_type)
        struct_b, text_b = extract(ver_b.filepath, doc.file_type)

        import difflib
        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()
        sm = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)

        changes = []
        para_num = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                para_num += (i2 - i1)
                continue
            if tag == 'replace':
                for idx in range(max(i2 - i1, j2 - j1)):
                    para_num += 1
                    old = lines_a[i1 + idx] if (i1 + idx) < i2 else ''
                    new = lines_b[j1 + idx] if (j1 + idx) < j2 else ''
                    if old and new:
                        changes.append({'type': 'Geändert', 'old': old[:300],
                                        'new': new[:300], 'para': para_num})
                    elif old:
                        changes.append({'type': 'Gelöscht', 'old': old[:300],
                                        'new': '', 'para': para_num})
                    else:
                        changes.append({'type': 'Eingefügt', 'old': '',
                                        'new': new[:300], 'para': para_num})
            elif tag == 'delete':
                for idx in range(i1, i2):
                    para_num += 1
                    changes.append({'type': 'Gelöscht',
                                    'old': lines_a[idx][:300],
                                    'new': '', 'para': para_num})
            elif tag == 'insert':
                for idx in range(j1, j2):
                    para_num += 1
                    changes.append({'type': 'Eingefügt', 'old': '',
                                    'new': lines_b[idx][:300],
                                    'para': para_num})

        if not changes:
            return jsonify({
                'status': 'ok',
                'analysis': 'Keine Änderungen gefunden.',
                'change_count': 0,
            })

        # Filter out trivial changes (whitespace-only, very short)
        significant_changes = []
        for ch in changes:
            old = (ch.get('old') or '').strip()
            new = (ch.get('new') or '').strip()
            # Skip whitespace-only or very short trivial changes
            if not old and not new:
                continue
            combined = old + new
            if len(combined) < 3:
                continue
            # Truncate text more aggressively for LLM prompt
            ch_copy = dict(ch)
            ch_copy['old'] = old[:200]
            ch_copy['new'] = new[:200]
            significant_changes.append(ch_copy)

        # Limit to 50 most significant changes to keep prompt manageable
        # Prefer longer/more substantial changes over short ones
        if len(significant_changes) > 50:
            significant_changes.sort(
                key=lambda c: len(c.get('old', '')) + len(c.get('new', '')),
                reverse=True)
            analysis_changes = significant_changes[:50]
            # Re-sort by paragraph number for logical order
            analysis_changes.sort(key=lambda c: c.get('para', 0))
            truncated = True
        else:
            analysis_changes = significant_changes
            truncated = len(changes) > len(significant_changes)

        result = analyze_changes(
            analysis_changes,
            client_party=client_party,
            document_context=document_context or doc.name,
            model=model,
            client_version=client_version,
            provider=provider,
        )

        if truncated:
            result['truncated'] = True
            result['total_changes'] = len(changes)

        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@api.route('/ai/export-docx', methods=['POST'])
def ai_export_docx():
    """Export AI analysis as a professional Word document with tables."""
    import tempfile
    from docx import Document as DocxDocument
    from docx.shared import Pt, RGBColor, Inches, Cm, Emu
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from datetime import datetime

    data = request.get_json() or {}
    issue_list = data.get('issue_list')
    client_party = data.get('client_party', 'Mandant')
    model_name = data.get('model', '')
    change_count = data.get('change_count', 0)

    # Fallback for unstructured
    if not issue_list:
        raw = data.get('analysis', data.get('raw', ''))
        issue_list = {'title': 'AI Issue List', 'sections': [],
                      'subtitle': f'Mandant: {client_party}',
                      'executive_summary': {'strategy': raw}}

    doc = DocxDocument()

    SEVERITY_COLORS = {
        'KRITISCH': RGBColor(220, 38, 38),
        'WICHTIG': RGBColor(234, 88, 12),
        'NEUTRAL': RGBColor(100, 100, 100),
        'VORTEILHAFT': RGBColor(22, 163, 74),
    }
    SEVERITY_BG = {
        'KRITISCH': 'FFCCCC',
        'WICHTIG': 'FFE4CC',
        'NEUTRAL': 'F5F5F5',
        'VORTEILHAFT': 'CCFFCC',
    }
    HEADER_BG = '1F3864'
    HEADER_TEXT = RGBColor(255, 255, 255)

    def set_cell_bg(cell, color_hex):
        shading = cell._element.get_or_add_tcPr()
        shd = shading.makeelement(qn('w:shd'), {
            qn('w:fill'): color_hex, qn('w:val'): 'clear'})
        shading.append(shd)

    def add_cell_text(cell, text, bold=False, size=8, color=None):
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(str(text) if text else '')
        run.font.size = Pt(size)
        run.font.name = 'Calibri'
        if bold:
            run.bold = True
        if color:
            run.font.color.rgb = color

    # ── Title ──
    title = doc.add_heading(issue_list.get('title', 'ISSUE LIST'), level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = RGBColor(31, 56, 100)

    # Subtitle
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run(f'{issue_list.get("subtitle", "")} | {model_name} | '
                    f'Erstellt: {datetime.now().strftime("%d.%m.%Y %H:%M")}')
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(128, 128, 128)

    # Confidential marker
    conf = doc.add_paragraph()
    conf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = conf.add_run('VERTRAULICH | NUR FÜR INTERNE ZWECKE')
    r.font.size = Pt(8)
    r.font.color.rgb = RGBColor(180, 0, 0)
    r.bold = True

    # ── Executive Summary ──
    summary = issue_list.get('executive_summary', {})
    if summary:
        doc.add_heading('EXECUTIVE SUMMARY', level=1)
        if summary.get('strategy'):
            p = doc.add_paragraph()
            p.add_run(summary['strategy']).font.size = Pt(10)

        # Summary stats table
        stats = []
        for key, label, color in [
            ('critical', 'Kritisch', 'FFCCCC'),
            ('important', 'Wichtig', 'FFE4CC'),
            ('neutral', 'Neutral', 'F5F5F5'),
            ('favorable', 'Vorteilhaft', 'CCFFCC'),
        ]:
            val = summary.get(key, 0)
            if val:
                stats.append((label, val, color))

        if stats:
            tbl = doc.add_table(rows=1, cols=len(stats))
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            for i, (label, val, bg) in enumerate(stats):
                cell = tbl.cell(0, i)
                set_cell_bg(cell, bg)
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(f'{label}: {val}')
                r.font.size = Pt(9)
                r.bold = True

        if summary.get('key_risks'):
            doc.add_heading('Kritische Punkte', level=2)
            for risk in summary['key_risks']:
                p = doc.add_paragraph(style='List Bullet')
                r = p.add_run(risk)
                r.font.size = Pt(10)

    # ── Sections with Issue Tables ──
    for section in issue_list.get('sections', []):
        sec_num = section.get('number', '')
        sec_title = section.get('title', '')
        doc.add_heading(f'{sec_num}. {sec_title}', level=1)

        if section.get('summary'):
            p = doc.add_paragraph()
            r = p.add_run(section['summary'])
            r.font.size = Pt(9)
            r.font.italic = True
            r.font.color.rgb = RGBColor(80, 80, 80)

        issues = section.get('issues', [])
        if not issues:
            continue

        # Create table: Ref | Issue/Change | Version A | Version B | Kommentar
        cols = 5
        tbl = doc.add_table(rows=1 + len(issues), cols=cols)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Header row
        headers = ['Ref.', 'Issue / Change', 'Version A\n(Alt)', 'Version B\n(Neu)', 'Kommentar']
        for i, h in enumerate(headers):
            cell = tbl.cell(0, i)
            set_cell_bg(cell, HEADER_BG)
            add_cell_text(cell, h, bold=True, size=8, color=HEADER_TEXT)

        # Data rows
        for row_idx, issue in enumerate(issues, 1):
            severity = issue.get('severity', 'NEUTRAL').upper()
            sev_bg = SEVERITY_BG.get(severity, 'F5F5F5')
            sev_color = SEVERITY_COLORS.get(severity, RGBColor(100, 100, 100))

            # Ref cell with severity background
            ref_cell = tbl.cell(row_idx, 0)
            set_cell_bg(ref_cell, sev_bg)
            p = ref_cell.paragraphs[0]
            r = p.add_run(issue.get('ref', ''))
            r.font.size = Pt(8)
            r.bold = True
            p.add_run('\n')
            label_txt = issue.get('label', '')
            if label_txt:
                r2 = p.add_run(label_txt)
                r2.font.size = Pt(7)
                r2.bold = True

            # Issue cell
            issue_cell = tbl.cell(row_idx, 1)
            p = issue_cell.paragraphs[0]
            # Severity badge
            sev_run = p.add_run(f'[{severity}] ')
            sev_run.font.size = Pt(7)
            sev_run.bold = True
            sev_run.font.color.rgb = sev_color
            # Issue text
            issue_run = p.add_run(issue.get('issue', ''))
            issue_run.font.size = Pt(8)
            # Recommendation
            rec = issue.get('recommendation', '')
            if rec:
                p.add_run('\n')
                rec_run = p.add_run(f'Empfehlung: {rec}')
                rec_run.font.size = Pt(7)
                rec_run.bold = True
                rec_run.font.color.rgb = sev_color

            # Old text
            old_cell = tbl.cell(row_idx, 2)
            add_cell_text(old_cell, issue.get('old_text', ''), size=7)

            # New text
            new_cell = tbl.cell(row_idx, 3)
            add_cell_text(new_cell, issue.get('new_text', ''), size=7)

            # Comment
            comment_cell = tbl.cell(row_idx, 4)
            add_cell_text(comment_cell, issue.get('comment', ''), size=7)

        # Set column widths
        for row in tbl.rows:
            row.cells[0].width = Cm(2.0)
            row.cells[1].width = Cm(6.0)
            row.cells[2].width = Cm(3.5)
            row.cells[3].width = Cm(3.5)
            row.cells[4].width = Cm(3.5)

        doc.add_paragraph()  # spacer

    # ── Footer ──
    doc.add_paragraph()
    footer = doc.add_paragraph()
    r = footer.add_run('Erstellt mit MyCompare AI — Automatische Analyse, keine Rechtsberatung.')
    r.font.size = Pt(8)
    r.font.color.rgb = RGBColor(160, 160, 160)
    r.italic = True

    tmpfile = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    doc.save(tmpfile.name)
    tmpfile.close()

    return send_from_directory(
        os.path.dirname(tmpfile.name),
        os.path.basename(tmpfile.name),
        as_attachment=True,
        download_name=f'IssueList_{client_party}.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
