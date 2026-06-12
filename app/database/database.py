
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from geoalchemy2 import Geometry

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/vmg_db")
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Territorio(Base):
    __tablename__ = "territorios"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    hash_transacao = Column(String(100), nullable=True)
    numero_car = Column(String(100), unique=True, nullable=True, index=True)
    nome_propriedade = Column(String(255), nullable=True)
    # Geometria em SIRGAS 2000 (SRID 4674) conforme sua tabela original
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=4674, spatial_index=True), nullable=True)
    area_hectares = Column(Numeric(10, 2), nullable=True)
    data_criacao = Column(DateTime, nullable=True)
    cultura_declarada = Column(String(255), nullable=True)
    usuario = Column(String(50), nullable=True)
    data_cadastro = Column(DateTime, default=datetime.utcnow)
    data_atualizacao = Column(DateTime, nullable=True)

    classificacoes = relationship("ClassificacaoCultura", back_populates="territorio", cascade="all, delete-orphan")

class ClassificacaoCultura(Base):
    __tablename__ = "classificacoes_culturas"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    territorio_id = Column(Integer, ForeignKey("agroprods.territorios.id", ondelete="CASCADE"), nullable=False)
    safra = Column(String(9), nullable=False, index=True)
    data_classificacao = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    cultura_predita = Column(String(50), nullable=False)
    cultura_real = Column(String(255), nullable=True)
    confianca_ia = Column(Float, nullable=False)

    territorio = relationship("Territorio", back_populates="classificacoes")

class DocumentoTecnico(Base):
    __tablename__ = "documentos_tecnicos"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False)
    tipo = Column(String(50), nullable=False)
    caminho_arquivo = Column(String(500), nullable=False)
    data_upload = Column(DateTime, default=datetime.utcnow, nullable=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
