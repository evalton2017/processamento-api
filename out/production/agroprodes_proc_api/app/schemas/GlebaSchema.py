from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional


class GlebaSchema(BaseModel):
    id_gleba: int
    id_produtor: int
    codigo_car: str
    cultura_declarada: Optional[str] = None
    geometria: str = Field(..., description="WKT ou formato GeoJSON da geometria")
    area_hectares: float
    data_estimada_plantio: Optional[date] = None
    data_criacao: datetime

    class Config:
        from_attributes = True
