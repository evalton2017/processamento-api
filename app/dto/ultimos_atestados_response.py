# app/dto/atestados_dashboard_dto.py
from datetime import datetime
from pydantic import BaseModel

class UltimosAtestadosResponse(BaseModel):
    codigo_gleba: str
    produtor: str
    municipio: str
    data: datetime
    area_ha: float

    class Config:
        from_attributes = True
