# app/models/gleba_model.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func, Numeric, Date, Text
from sqlalchemy.orm import relationship, foreign
from geoalchemy2 import Geometry

from app.database.session import Base
from app.models.notificacao_model import NotificacaoUsuarioModel
from app.models.models_ledger import AtestadosVmgLedger
# Importamos o modelo do ledger do schema audit que centralizará a inteligência de conformidade
from app.models.models_ledger import HistoricoLaudosAmbientaisLedger

class GlebaModel(Base):
    __tablename__ = "glebas"
    __table_args__ = {"schema": "agroprods"}

    id_gleba = Column(Integer, primary_key=True, index=True)
    id_produtor = Column(Integer, nullable=False)
    codigo_car = Column(String(50), nullable=True)
    codigo_municipio = Column(Integer, ForeignKey("agroprods.municipio_ibge.codigo_municipio"), nullable=True)

    # CORREÇÃO CRÍTICA: Ajustado para o tipo Geometry para suportar as consultas espaciais do PostGIS
    geometria = Column(Geometry("POLYGON", srid=4326), nullable=False)

    area_hectares = Column(Numeric(10, 2), nullable=False)
    volume_declarado_comercializar = Column(Numeric(10, 2), nullable=False)
    data_estimada_colheita = Column(DateTime, nullable=True)
    data_criacao = Column(DateTime, server_default=func.now())
    data_estimada_plantio = Column(DateTime, nullable=True)
    cultura_declarada = Column(String(255), nullable=True)

    municipio = relationship("MunicipioIbge", back_populates="glebas", lazy="select")
    notificacoes = relationship("NotificacaoUsuarioModel", back_populates="gleba", cascade="all, delete-orphan")

    # Relacionamento unificado com o livro-razão de laudos ambientais (Schema audit)
    laudos_ledger = relationship(
        "HistoricoLaudosAmbientaisLedger",
        primaryjoin="GlebaModel.id_gleba == foreign(HistoricoLaudosAmbientaisLedger.id_gleba)",
        viewonly=True,
        order_by="desc(HistoricoLaudosAmbientaisLedger.id_laudo)",
        lazy="select"
    )

    atestados_ledger = relationship(
        "AtestadosVmgLedger",
        primaryjoin="GlebaModel.id_gleba == foreign(AtestadosVmgLedger.id_gleba)",
        viewonly=True
    )


class MunicipioIbge(Base):
    __tablename__ = "municipio_ibge"
    __table_args__ = {"schema": "agroprods"}

    codigo_municipio = Column(Integer, primary_key=True, index=True)
    nome_municipio = Column(String(255), nullable=False)
    codigo_uf = Column(Integer, nullable=False)
    sigla_uf = Column(String(2), nullable=False, index=True)
    estado = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    ddd = Column(Integer, nullable=True)

    glebas = relationship("GlebaModel", back_populates="municipio")


class DocumentoTecnico(Base):
    __tablename__ = "documentos_tecnicos"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False)
    tipo = Column(String(50), nullable=False)
    caminho_arquivo = Column(String(500), nullable=False)
    data_upload = Column(DateTime, default=func.now(), nullable=False)


class MetadadosRaster(Base):
    __tablename__ = "metadados_raster"
    __table_args__ = {"schema": "agroprods"}

    id_raster = Column(Integer, primary_key=True, autoincrement=True)
    id_gleba = Column(Integer, nullable=True)
    data_captura = Column(Date, nullable=False)
    ndvi_mean = Column(Float, nullable=True)
    ndvi_std = Column(Float, nullable=True)
    cloud_cover = Column(Float, nullable=True)
    raster_url = Column(Text, nullable=False)
    hash_sha256 = Column(String(64), nullable=True)

    geom = Column(Geometry("GEOMETRY", srid=4326), nullable=True)
