# app/models/agricola.py
from sqlalchemy import Column, Integer, String, Numeric, Date, Index
from app.database.session import Base

class ZarcZoneamento(Base):
    """
    Representa a tabela 'agroprods.zarc_zoneamento' utilizada para validar
    as janelas de risco climático declaradas no Planejamento Agronômico.
    """
    __tablename__ = "zarc_zoneamento"

    # Ajuste fino: Tupla com vírgula no fechamento do dicionário para validação do Python
    __table_args__ = (
        Index("idx_zarc_municipio", "municipio_ibge", "cultura"),
        {"schema": "agroprods"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    municipio_ibge = Column(Integer, nullable=False)
    cultura = Column(String(50), nullable=False)
    tipo_solo = Column(String(10), nullable=True)
    grupo_risco = Column(String(20), nullable=True)
    decendio_plantio = Column(Integer, nullable=True)

    # numeric(5, 2) mapeado com precisão para evitar quebras em ponto flutuante
    risco_admissivel = Column(Numeric(5, 2), nullable=True)
    data_atualizacao = Column(Date, nullable=True)
