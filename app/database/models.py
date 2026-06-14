from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import Integer, String, Numeric, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

class Base(DeclarativeBase):
    pass

class Pessoa(Base):
    __tablename__ = "pessoa"
    __table_args__ = {"schema": "agroprods"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    id_keycloak: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)

    glebas: Mapped[List["Gleba"]] = relationship("Gleba", back_populates="produtor")


class Gleba(Base):
    __tablename__ = "glebas"
    __table_args__ = {"schema": "agroprods"}

    id_gleba: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_produtor: Mapped[int] = mapped_column(Integer, ForeignKey("agroprods.pessoa.id"), nullable=False)
    codigo_car: Mapped[Optional[str]] = mapped_column(String(50))
    cultura_declarada: Mapped[Optional[str]] = mapped_column(String(255))
    # Geometria definida como Polygon em EPSG:4326 conforme o seu script
    geometria: Mapped[Any] = mapped_column(Geometry(geometry_type="Polygon", srid=4326), nullable=False)
    area_hectares: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    data_estimada_plantio: Mapped[Optional[datetime]] = mapped_column(DateTime)
    data_criacao: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    produtor: Mapped["Pessoa"] = relationship("Pessoa", back_populates="glebas")
    classificacoes: Mapped[List["ClassificacaoCultura"]] = relationship("ClassificacaoCultura", back_populates="gleba")


class ClassificacaoCultura(Base):
    __tablename__ = "classificacoes_culturas"
    __table_args__ = {"schema": "agroprods"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gleba_id: Mapped[int] = mapped_column(Integer, ForeignKey("agroprods.glebas.id_gleba"), nullable=False)
    safra: Mapped[str] = mapped_column(String(50), nullable=False)
    data_classificacao: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    cultura_predita: Mapped[str] = mapped_column(String(50), nullable=False)
    cultura_real: Mapped[str] = mapped_column(String(50), nullable=False)
    confianca_ia: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)

    # Colunas customizadas acopladas para suporte à IA Real e Regras de Negócio
    produtividade_sacas_ha: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    nitrogenio_grid: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    prodes_conflito: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bpa_status: Mapped[bool] = mapped_column(Boolean, nullable=False)
    srid_validado: Mapped[int] = mapped_column(Integer, default=4326)

    # Colunas de Auditoria Criptográfica (Ledger Blockchain)
    blockchain_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    blockchain_anterior: Mapped[str] = mapped_column(String(64), nullable=False)

    gleba: Mapped["Gleba"] = relationship("Gleba", back_populates="classificacoes")


class AnaliseProdes(Base):
    __tablename__ = "analise_prodes"
    __table_args__ = {"schema": "agroprods"}

    id_analise: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_imagem: Mapped[Optional[int]] = mapped_column(Integer)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    geometry: Mapped[Any] = mapped_column(Geometry(geometry_type="Geometry", srid=4326))
    geometry_unificado: Mapped[Optional[Any]] = mapped_column(Geometry(geometry_type="Geometry", srid=4326))
    analisado: Mapped[Optional[bool]] = mapped_column(Boolean)
    status: Mapped[Optional[str]] = mapped_column(String(50))
    usuario: Mapped[Optional[str]] = mapped_column(String(100))
    image_url: Mapped[Optional[str]] = mapped_column(String(255))


class PropriedadeSoloGrid(Base):
    __tablename__ = "propriedades_solo_grid"
    __table_args__ = {"schema": "agroprods"}

    id_ponto: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_gleba: Mapped[int] = mapped_column(Integer, ForeignKey("agroprods.glebas.id_gleba"), nullable=False)
    coordenada: Mapped[Any] = mapped_column(Geometry(geometry_type="Point", srid=4326))
    materia_organica_nivel: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    saude_plantas_ndvi: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    nitrogenio_nivel: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    cor_hex_exibicao: Mapped[Optional[str]] = mapped_column(String(7))