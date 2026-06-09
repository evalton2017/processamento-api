from pydantic import BaseModel, Field
from typing import List
from app.schemas.clima import IndicadoresAcumulados, AlertaClimatico

class ResumoIA(BaseModel):
    cultura_identificada: str
    assertividade_score: float
    data_estimada_plantio: str
    data_estimada_colheita: str

class ResumoProdutividade(BaseModel):
    produtividade_estimada_sc_ha: float
    volume_total_estimado_sacas: float
    volume_declarado_condizente: bool

class RespostaCadernoCampo(BaseModel):
    id_gleba: int
    safra_ano: str = Field(..., example="2025/2026")
    area_hectares: float
    analise_vegetativa_ia: ResumoIA
    diagnostico_climatico: IndicadoresAcumulados
    alertas_ambientais_emitidos: List[AlertaClimatico]
    validacao_comercial: ResumoProdutividade
