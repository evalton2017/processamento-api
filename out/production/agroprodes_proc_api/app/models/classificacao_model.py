from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, func, BigInteger, Numeric
from sqlalchemy.orm import relationship
from app.database.session import Base

class CertificadosBpa(Base):
    __tablename__ = "certificados_bpa"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    produtor_id = Column(Integer, nullable=False, index=True)
    codigo_certificado = Column(String(100), nullable=False, unique=True)
    status = Column(String(50), nullable=False)
    data_emissao = Column(Date, nullable=False)
    data_validade = Column(Date, nullable=False)


class ClassificacoesCulturas(Base):
    __tablename__ = "classificacoes_culturas"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    gleba_id = Column(Integer, ForeignKey("agroprods.glebas.id_gleba"), nullable=False)

    safra = Column(String(20), nullable=False, index=True)
    data_classificacao = Column(DateTime, default=datetime.utcnow)
    cultura_predita = Column(String(100), nullable=False, index=True)
    cultura_real = Column(String(100), nullable=True)
    confianca_ia = Column(Float, nullable=False)
    produtividade_sacas_ha = Column(Float, nullable=True)
    nitrogenio_grid = Column(String(100), nullable=True)
    prodes_conflito = Column(Boolean, default=False)
    bpa_status = Column(Boolean, default=False)
    srid_validado = Column(Integer, nullable=False)
    blockchain_hash = Column(String(255), nullable=True)
    blockchain_anterior = Column(String(255), nullable=True)

    gleba = relationship("GlebaModel", back_populates="classificacoes")


class EstacaoInmet(Base):
    __tablename__ = "estacoes_inmet"
    __table_args__ = {"schema": "agroprods"}

    # id mapeado como String(10) para bater com o varchar(10) NOT NULL PRIMARY KEY
    id = Column(String(10), primary_key=True)
    nome = Column(String(100), nullable=False)
    uf = Column(String(100), nullable=True)

    # Coordenadas e altitude como Numeric de acordo com o DDL
    latitude = Column(Numeric(9, 6), nullable=False)
    longitude = Column(Numeric(9, 6), nullable=False)
    altitude = Column(Numeric(9, 6), nullable=True)

    data = Column(DateTime, server_default=func.now(), nullable=True)
    status = Column(String(15), server_default="OPERANTE", nullable=False)

    # Relacionamento puramente lógico (nível de aplicação), usando amarração de strings
    series_diarias = relationship(
        "SerieClimaticaDiaria",
        primaryjoin="EstacaoInmet.id == SerieClimaticaDiaria.id_estacao",
        foreign_keys="[SerieClimaticaDiaria.id_estacao]",
        back_populates="estacao"
    )


class SerieClimaticaDiaria(Base):
    __tablename__ = "series_climaticas_diarias"
    __table_args__ = {"schema": "agroprods"}

    # id_serie mapeado como BigInteger para suportar o bigserial do Postgres
    id_serie = Column(BigInteger, primary_key=True, autoincrement=True)

    # id_estacao mapeado estritamente como String(10) para casar com o varchar(10)
    id_estacao = Column(String(10), nullable=False)

    data = Column(Date, nullable=False)

    # Tipos numéricos com suas respectivas precisões e escalas
    chuva_mm = Column(Numeric(6, 2), server_default="0.00", nullable=False)
    temp_c = Column(Numeric(4, 1), nullable=False)
    vento_velocidade = Column(Numeric(5, 2), nullable=True)

    data_registro = Column(DateTime, server_default=func.now(), nullable=True)

    # Relacionamento reverso puramente lógico
    estacao = relationship(
        "EstacaoInmet",
        primaryjoin="SerieClimaticaDiaria.id_estacao == EstacaoInmet.id",
        foreign_keys="[SerieClimaticaDiaria.id_estacao]",
        back_populates="series_diarias"
    )