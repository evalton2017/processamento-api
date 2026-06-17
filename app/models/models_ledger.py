from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Boolean, JSON
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database.session import Base
# ==============================================================================
# 1. PILAR DE CERTIFICAÇÃO E SEGURO AGRÍCOLA (Item 2)
# ==============================================================================

class AtestadosVmgLedger(Base):
    __tablename__ = "atestados_vmg_ledger"
    __table_args__ = {"schema": "audit"}

    id_bloco = Column(Integer, primary_key=True)
    id_gleba = Column(Integer, ForeignKey("agroprods.glebas.id_gleba"), nullable=False)

    gleba = relationship(
        "app.models.gleba_model.GlebaModel",
        primaryjoin="AtestadosVmgLedger.id_gleba == foreign(GlebaModel.id_gleba)",
        viewonly=True
    )


# ==============================================================================
# 2. PILAR DE GOVERNANÇA E SEGURANÇA JURÍDICA (LGPD)
# ==============================================================================

class ConsentimentoLgpdLedger(Base):
    __tablename__ = "consentimento_lgpd_ledger"
    __table_args__ = {"schema": "audit"}

    id_consentimento = Column(Integer, primary_key=True, index=True)
    id_produtor = Column(Integer, nullable=False, index=True)
    autorizado_cruzamento_car = Column(Boolean, default=True, nullable=True)
    data_consentimento = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_origem = Column(String(45), nullable=False)
    dispositivo_token = Column(String, nullable=False)
    hash_registro = Column(String, nullable=False)


# ==============================================================================
# 3. PILAR DE DECISÕES E INFERÊNCIAS DA IA (Itens 3.1, 3.4-a e 3.6-d-I)
# ==============================================================================

class IaClassificacaoCulturaLedger(Base):
    __tablename__ = "ia_classificacao_cultura_ledger"
    __table_args__ = {"schema": "audit"}

    id_classificacao = Column(Integer, primary_key=True, index=True)
    id_gleba = Column(Integer, ForeignKey("agroprods.glebas.id_gleba"), nullable=False)
    safra = Column(String(9), nullable=False)
    cultura_identificada = Column(String(50), nullable=False)
    cultura_declarada = Column(String(50), nullable=False)
    status_conducao = Column(String(20), nullable=False)
    percentual_confianca = Column(Numeric(5, 2), nullable=False)
    data_analise = Column(DateTime, default=datetime.utcnow, nullable=False)
    hash_bloco = Column(String, nullable=False)

    gleba = relationship("GlebaModel", foreign_keys=[id_gleba])


class IaEstimativaProdutividadeLedger(Base):
    __tablename__ = "ia_estimativa_produtividade_ledger"
    __table_args__ = {"schema": "audit"}

    id_estimativa = Column(Integer, primary_key=True, index=True)
    id_gleba = Column(Integer, ForeignKey("agroprods.glebas.id_gleba"), nullable=False)
    safra = Column(String(9), nullable=False)
    produtividade_ia_sacas_ha = Column(Numeric(10, 2), nullable=False)
    volume_comercializar_declarado = Column(Numeric(12, 2), nullable=False)
    status_compatibilidade = Column(String(20), nullable=False)
    data_calculo = Column(DateTime, default=datetime.utcnow, nullable=False)
    hash_bloco = Column(String, nullable=False)

    gleba = relationship("GlebaModel", foreign_keys=[id_gleba])


# ==============================================================================
# 4. PILAR DE COMPLIANCE AMBIENTAL E LAUDOS DE CONFORMIDADE (Item 2 e 2.1)
# ==============================================================================

class HistoricoLaudosAmbientaisLedger(Base):
    __tablename__ = "historico_laudos_ambientais_ledger"
    __table_args__ = {"schema": "audit"}

    id_laudo = Column(Integer, primary_key=True, index=True)
    id_gleba = Column(Integer, ForeignKey("agroprods.glebas.id_gleba"), nullable=False)
    conflito_socioambiental = Column(Boolean, nullable=False)
    conflito_prodes = Column(Boolean, nullable=False)
    conflito_ibama_icmbio = Column(Boolean, nullable=False)
    conflito_comunidades = Column(Boolean, nullable=False)
    raio_analisado_metros = Column(Numeric(6, 1), default=500.0, nullable=False)
    data_auditoria = Column(DateTime, default=datetime.utcnow, nullable=False)
    laudo_detalhado_json = Column(JSON, nullable=False)  # Armazena o dump do laudo
    hash_bloco = Column(String, nullable=False)

    gleba = relationship("GlebaModel", foreign_keys=[id_gleba])


# ==============================================================================
# 5. PILAR DE DECLARAÇÕES DO PRODUTOR E VALIDACÃO ZARC/BPA (Item 3.6)
# ==============================================================================

class DeclaracaoGlebaPeriodoLedger(Base):
    __tablename__ = "declaracao_gleba_periodo_ledger"
    __table_args__ = {"schema": "audit"}

    id_declaracao = Column(Integer, primary_key=True, index=True)
    id_gleba = Column(Integer, ForeignKey("agroprods.glebas.id_gleba"), nullable=False)
    id_produtor = Column(Integer, nullable=False, index=True)
    cultura_declarada = Column(String(50), nullable=False)
    data_estimada_plantio = Column(DateTime, nullable=False)
    data_estimada_colheita = Column(DateTime, nullable=False)
    decendio_plantio_zarc = Column(Integer, nullable=False)
    risco_zarc_admissivel = Column(Numeric(5, 2), nullable=False)
    possui_certificado_bpa = Column(Boolean, nullable=False)
    data_registro = Column(DateTime, default=datetime.utcnow, nullable=False)
    hash_bloco = Column(String, nullable=False)

    gleba = relationship("GlebaModel", foreign_keys=[id_gleba])
