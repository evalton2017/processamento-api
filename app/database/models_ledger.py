from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, func, Numeric
from app.database.session import Base

class ConsentimentoLgpdLedgerModel(Base):
    __tablename__ = "consentimento_lgpd_ledger"
    # Vincula rigidamente esta tabela ao esquema 'audit' na base remota ledger_db
    __table_args__ = {"schema": "audit"}

    id_consentimento = Column(Integer, primary_key=True, index=True)
    id_produtor = Column(Integer, nullable=False)
    autorizado_cruzamento_car = Column(Boolean, default=True)
    data_consentimento = Column(DateTime, server_default=func.now())
    ip_origem = Column(String(45), nullable=False)
    dispositivo_token = Column(Text, nullable=False)


class AtestadosVmgLedgerModel(Base):
    __tablename__ = "atestados_vmg_ledger"
    __table_args__ = {"schema": "audit"}

    id_atestado = Column(Integer, primary_key=True, index=True)
    id_gleba = Column(Integer, nullable=False)
    tipo_contrato = Column(String(20), nullable=False)
    status_validacao = Column(String(20), nullable=False)
    estimativa_produtividade_sacas = Column(Numeric(10, 2), nullable=True)
    data_emissao = Column(DateTime, server_default=func.now())
    hash_relatorio = Column(Text, nullable=False)
