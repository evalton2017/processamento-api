from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func, Numeric
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from app.database.database import SessionLocal
from app.database.session import Base

class GlebaModel(Base):
    __tablename__ = "glebas"
    __table_args__ = {"schema": "agroprods"}

    id_gleba = Column(Integer, primary_key=True, index=True)
    id_produtor = Column(Integer, nullable=False)
    codigo_car = Column(String(50), nullable=True)
    geometria = Column(Geometry(geometry_type='POLYGON', srid=4326), nullable=False) # CRS EPSG:4326
    area_hectares = Column(Numeric(10, 2), nullable=False)
    data_criacao = Column(DateTime, server_default=func.now())
    data_estimada_plantio = Column(DateTime, nullable=True)
    cultura_declarada = Column(String(255), nullable=True)

    # Corrigido para apontar estritamente para a classe string 'ClassificacaoCultura'
    classificacoes = relationship("ClassificacaoCultura", back_populates="gleba", cascade="all, delete-orphan")


class ClassificacaoCultura(Base):
    __tablename__ = "classificacoes_culturas"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    # Chave estrangeira referenciando estritamente a tabela e coluna físicas do Postgres
    gleba_id = Column(Integer, ForeignKey("agroprods.glebas.id_gleba", ondelete="CASCADE"), nullable=False)
    safra = Column(String(9), nullable=False, index=True)
    data_classificacao = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    cultura_predita = Column(String(50), nullable=False)
    cultura_real = Column(String(255), nullable=True)
    confianca_ia = Column(Float, nullable=False)

    # CORREÇÃO CRÍTICA: Alterado de "Gleba" para "GlebaModel" para espelhar a classe declarada acima
    gleba = relationship("GlebaModel", back_populates="classificacoes")


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
