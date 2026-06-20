from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional

class EmbargoOrgaoSchema(BaseModel):
    id: int
    orgao_emissor: str
    num_termo: str
    cpf_cnpj_infrator: str
    nome_infrator: str
    data_embargo: date
    situacao: str = Field(..., description="Ex: Ativo, Inativo")
    data_cadastro: datetime

    class Config:
        from_attributes = True