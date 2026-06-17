from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey
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
