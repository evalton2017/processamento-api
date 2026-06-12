from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class ClassificacaoResponse(BaseModel):
    id: int
    territorio_id: int
    safra: str
    data_classificacao: datetime
    cultura_predita: str
    cultura_real: Optional[str]
    confianca_ia: float

    class Config:
        from_attributes = True

class MetricasAssertividadeResponse(BaseModel):
    total_amostras: int
    verdadeiros_positivos: int
    falsos_positivos: int
    falsos_negativos: int
    exatidao_global: float = Field(..., description="Fórmula: (VP + VN) / Total")
    precisao: float = Field(..., description="Fórmula: VP / (VP + FP)")
    revocacao_sensibilidade: float = Field(..., description="Fórmula: VP / (VP + FN)")
    f1_score: float = Field(..., description="Média harmônica entre precisão e revocação")

class DocumentoResponse(BaseModel):
    id: int
    titulo: str
    tipo: str
    caminho_arquivo: str
    data_upload: datetime

    class Config:
        from_attributes = True
