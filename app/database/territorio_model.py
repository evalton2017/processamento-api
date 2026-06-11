from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TerritorioModel(Base):
    __tablename__ = "territorios"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    hash_transacao = Column(String(100), nullable=True)
    numero_car = Column(String(100), unique=True, nullable=True)
    nome_propriedade = Column(String(255), nullable=True)
    geometria = Column(
        Geometry(geometry_type="GEOMETRY", srid=4674), nullable=True
    )
    area_hectares = Column(Numeric(10, 2), nullable=True)
    data_criacao = Column(DateTime, nullable=True)
    cultura_declarada = Column(String(255), nullable=True)
    usuario = Column(String(50), nullable=True)
    data_cadastro = Column(DateTime, server_default=func.now())
    data_atualizacao = Column(DateTime, nullable=True)
