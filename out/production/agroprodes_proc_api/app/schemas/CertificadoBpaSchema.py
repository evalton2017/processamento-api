from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional

class CertificadoBpaSchema(BaseModel):
    id: int
    produtor_id: int
    codigo_certified: str
    status: str
    data_emissao: date
    data_validade: date

    class Config:
        from_attributes = True