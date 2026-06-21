# app/dto/atestados_dashboard_dto.py
from datetime import datetime
from pydantic import BaseModel

from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class UltimosAtestadosResponse(BaseModel):
    evento: str
    municipio: str
    data: datetime
    # Mapeando os campos booleanos/estatísticos retornados pela sua query
    conflito_socioambiental: Optional[bool] = None
    conflito_prodes: Optional[bool] = None
    glebas_afetadas: int

    # Adicionando como opcionais com valor padrão None para compatibilidade
    # e para evitar o travamento do ResponseValidationError do FastAPI
    codigo_gleba: Optional[str] = None
    produtor: Optional[str] = None
    area_ha: Optional[float] = None

    class Config:
        from_attributes = True
