from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime

from app.database.session import Base


class EmbargosOrgaos(Base):
    __tablename__ = "embargos_orgaos"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    orgao_emissor = Column(String(150), nullable=False)
    num_termo = Column(String(100), nullable=False)
    cpf_cnpj_infrator = Column(String(20), nullable=False)
    nome_infrator = Column(String(255), nullable=False)
    data_embargo = Column(DateTime, nullable=False)
    situacao = Column(String(50), nullable=False, index=True) # Ex: 'Ativo', 'Inativo'
    data_cadastro = Column(DateTime, default=datetime.utcnow)