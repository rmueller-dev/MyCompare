from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, '..', 'mycompare.db')
STORAGE_DIR = os.path.join(BASE_DIR, '..', 'storage')

engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False)
    file_type = Column(String(10), nullable=False)  # docx, xlsx, pptx, pdf
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    versions = relationship('Version', back_populates='document', order_by='Version.version_number')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'file_type': self.file_type,
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


def init_db():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    Base.metadata.create_all(engine)
