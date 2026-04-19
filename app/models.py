from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone
import os
import json

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, '..', 'mycompare.db')
STORAGE_DIR = os.path.join(BASE_DIR, '..', 'storage')

engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Folder(Base):
    __tablename__ = 'folders'
    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False)
    parent_id = Column(Integer, ForeignKey('folders.id'), nullable=True)
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    children = relationship('Folder', backref='parent', remote_side=[id],
                            foreign_keys=[parent_id], lazy='select')
    documents = relationship('Document', back_populates='folder')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'parent_id': self.parent_id,
            'archived': self.archived,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'document_count': len(self.documents) if self.documents else 0,
        }


class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False)
    file_type = Column(String(10), nullable=False)  # docx, xlsx, pptx, pdf
    folder_id = Column(Integer, ForeignKey('folders.id'), nullable=True)
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    versions = relationship('Version', back_populates='document', order_by='Version.version_number')
    folder = relationship('Folder', back_populates='documents')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'file_type': self.file_type,
            'folder_id': self.folder_id,
            'archived': self.archived,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'versions': [v.to_dict() for v in self.versions],
        }


class Version(Base):
    __tablename__ = 'versions'
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False)
    version_number = Column(Integer, nullable=False)
    filename = Column(String(500), nullable=False)
    filepath = Column(String(1000), nullable=False)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    label = Column(Text, nullable=True)
    document = relationship('Document', back_populates='versions')

    def to_dict(self):
        return {
            'id': self.id,
            'document_id': self.document_id,
            'version_number': self.version_number,
            'filename': self.filename,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'label': self.label,
        }


class RenderingSet(Base):
    """Saved comparison profile with colors, markup styles, and comparison options."""
    __tablename__ = 'rendering_sets'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    settings_json = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    @property
    def settings(self):
        try:
            return json.loads(self.settings_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @settings.setter
    def settings(self, value):
        self.settings_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'is_default': self.is_default,
            'settings': self.settings,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


def init_db():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    Base.metadata.create_all(engine)

    # Migrate: add new columns if they don't exist yet
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    doc_cols = [c['name'] for c in insp.get_columns('documents')]
    with engine.begin() as conn:
        if 'folder_id' not in doc_cols:
            conn.execute(text('ALTER TABLE documents ADD COLUMN folder_id INTEGER REFERENCES folders(id)'))
        if 'archived' not in doc_cols:
            conn.execute(text('ALTER TABLE documents ADD COLUMN archived BOOLEAN DEFAULT 0'))

    # Create default rendering sets if none exist
    session = SessionLocal()
    try:
        if session.query(RenderingSet).count() == 0:
            defaults = [
                RenderingSet(
                    name='Standard',
                    description='Standard-Vergleichsprofil mit Litera-ähnlichen Farben',
                    is_default=True,
                    settings_json=json.dumps({
                        'colors': {
                            'deletion': '#DC2626',
                            'insertion': '#2563EB',
                            'move': '#16A34A',
                            'formatting': '#E65100',
                            'table': '#00695C',
                        },
                        'markup': {
                            'deletion_style': 'strikethrough',
                            'insertion_style': 'double-underline',
                            'move_style': 'strikethrough',
                        },
                        'options': {
                            'ignore_whitespace': False,
                            'ignore_case': False,
                            'ignore_headers_footers': False,
                            'character_level': False,
                            'compare_images': True,
                            'compare_formatting': True,
                        },
                    }),
                ),
                RenderingSet(
                    name='Nur Text',
                    description='Vergleicht nur Textinhalt, ignoriert Formatierung und Bilder',
                    settings_json=json.dumps({
                        'colors': {
                            'deletion': '#B91C1C',
                            'insertion': '#1D4ED8',
                            'move': '#15803D',
                            'formatting': '#9A3412',
                            'table': '#115E59',
                        },
                        'markup': {
                            'deletion_style': 'strikethrough',
                            'insertion_style': 'underline',
                            'move_style': 'strikethrough',
                        },
                        'options': {
                            'ignore_whitespace': True,
                            'ignore_case': False,
                            'ignore_headers_footers': False,
                            'character_level': False,
                            'compare_images': False,
                            'compare_formatting': False,
                        },
                    }),
                ),
                RenderingSet(
                    name='Detailliert',
                    description='Zeichenebene-Vergleich mit allen Details',
                    settings_json=json.dumps({
                        'colors': {
                            'deletion': '#EF4444',
                            'insertion': '#3B82F6',
                            'move': '#22C55E',
                            'formatting': '#F97316',
                            'table': '#14B8A6',
                        },
                        'markup': {
                            'deletion_style': 'strikethrough',
                            'insertion_style': 'double-underline',
                            'move_style': 'strikethrough',
                        },
                        'options': {
                            'ignore_whitespace': False,
                            'ignore_case': False,
                            'ignore_headers_footers': False,
                            'character_level': True,
                            'compare_images': True,
                            'compare_formatting': True,
                        },
                    }),
                ),
            ]
            for rs in defaults:
                session.add(rs)
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
