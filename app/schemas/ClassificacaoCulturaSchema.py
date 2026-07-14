from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional

class ClassificacaoCulturaSchema(BaseModel):
    id: int
    gleba_id: int
    safra: str
    data_classificacao: datetime
    cultura_predita: str
    cultura_real: Optional[str] = None
    confianca_ia: float
    produtividade_sacas_ha: Optional[float] = None
    nitrogenio_grid: Optional[str] = None
    prodes_conflito: bool
    bpa_status: bool
    srid_validado: int
    blockchain_hash: str
    blockchain_anterior: str

    class Config:
        from_attributes = True