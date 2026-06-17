# app/models/gleba_model.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func, Numeric
from sqlalchemy.orm import relationship

from app.database.session import Base

from app.models.classificacao_model import ClassificacoesCulturas
from app.models.notificacao_model import NotificacaoUsuarioModel
from app.models.models_ledger import AtestadosVmgLedger
# =============================================================

class GlebaModel(Base):
    __tablename__ = "glebas"
    __table_args__ = {"schema": "agroprods"}

    id_gleba = Column(Integer, primary_key=True, index=True)
    id_produtor = Column(Integer, nullable=False)
    codigo_car = Column(String(50), nullable=True)
    codigo_municipio = Column(Integer, ForeignKey("agroprods.municipio_ibge.codigo_municipio"), nullable=True)
    geometria = Column(String, nullable=False)
    area_hectares = Column(Numeric(10, 2), nullable=False)
    data_criacao = Column(DateTime, server_default=func.now())
    data_estimada_plantio = Column(DateTime, nullable=True)
    cultura_declarada = Column(String(255), nullable=True)

    municipio = relationship("MunicipioIbge", back_populates="glebas", lazy="select")

    # Agora o SQLAlchemy encontrará a classe perfeitamente em qualquer thread/processo
    classificacoes = relationship("ClassificacoesCulturas", back_populates="gleba", cascade="all, delete-orphan")
    notificacoes = relationship("NotificacaoUsuarioModel", back_populates="gleba", cascade="all, delete-orphan")

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
    data_upload = Column(DateTime, default=datetime.utcnow, nullable=False)
