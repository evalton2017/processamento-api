from sqlalchemy import Column, Integer, String, Numeric, DateTime, func
from geoalchemy2 import Geometry  # Certifique-se de ter 'geoalchemy2' instalado para dados PostGIS
from app.database.session import Base

class GlebaModel(Base):
    __tablename__ = "glebas"
    # Vincula rigidamente esta tabela ao esquema 'agroprods' no banco principal
    __table_args__ = {"schema": "agroprods"}

    id_gleba = Column(Integer, primary_key=True, index=True)
    id_produtor = Column(Integer, nullable=False)
    codigo_car = Column(String(50), nullable=True)
    geometria = Column(Geometry(geometry_type='POLYGON', srid=4326), nullable=False) # CRS EPSG:4326
    area_hectares = Column(Numeric(10, 2), nullable=False)
    data_criacao = Column(DateTime, server_default=func.now())
