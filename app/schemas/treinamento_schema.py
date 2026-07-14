from pydantic import BaseModel, Field
from datetime import date
from typing import Dict, Any

class TriggerCapturaRealRequest(BaseModel):
    id_gleba: int = Field(..., description="ID único para controle da gleba de treinamento", example=9500)
    cultura_real: str = Field(..., description="Rótulo verdadeiro / Ground Truth (Ex: SOJA, MILHO, CAFE)", example="SOJA")
    safra: str = Field(..., description="Safra correspondente ao ciclo histórico (Ex: 2024/2025)", example="2024/2025")
    data_inicio: date = Field(..., description="Data de início do ciclo fenológico (Plantio - 30 dias)", example="2024-10-15")
    data_fim: date = Field(..., description="Data de fim do ciclo fenológico (Próxima à colheita)", example="2025-03-15")
    geometria_wkt: str = Field(
        ...,
        description="Polígono da área em formato WKT (EPSG:4326)",
        example="POLYGON((-47.9200 -15.7500, -47.9100 -15.7500, -47.9100 -15.7600, -47.9200 -15.7600, -47.9200 -15.7500))"
    )

class TriggerCapturaRealResponse(BaseModel):
    status: str = Field(..., example="SUCESSO_CAPTURA_VMG")
    gleba_id: int = Field(..., example=9500)
    imagens_processadas: int = Field(..., example=18)
    mensagem: str = Field(..., example="Assinatura fenológica real extraída e salva para treinamento.")

class RetreinoClassificadorResponse(BaseModel):
    status: str = Field(..., example="XGBOOST_RECALIBRADO")
    total_registros_treino: int = Field(..., example=1)
    classes_aprendidas: list = Field(..., example=["SOJA", "MILHO"])
    caminho_modelo: str = Field(..., example=".../modelos/classificador_culturas.pkl")
    mensagem: str = Field(..., example="Classificador atualizado com dados fenológicos reais do satélite.")