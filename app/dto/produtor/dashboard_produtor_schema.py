from pydantic import BaseModel, Field
from typing import List, Dict, Any

class RespostaDashboardProdutorDTO(BaseModel):
    produtor_nome: str = Field(..., example="João Silva")
    safra_selecionada: str = Field(..., example="2025/2026")

    # Blocos visuais do painel do produtor
    glebas_ativas_total: int
    glebas_monitoradas_pct: float
    conformidade_ambiental_pct: float
    area_conforme_ha: float
    area_total_ha: float
    total_municipios: int
    atestados_emitidos_total: int
    alertas_total: int
    proxima_validacao_data: str

class LinhaCriterioConformidadeDTO(BaseModel):
    criterio: str = Field(..., example="APP")
    status: str = Field(..., example="Conforme") # 'Conforme', 'Atenção' ou 'Não Conforme'
    area_ha: float = Field(..., example=1156.40)
    percentual: int = Field(..., example=89)

class RespostaConformidadeAmbientalDTO(BaseModel):
    id_gleba: int
    criterios: List[LinhaCriterioConformidadeDTO]
    conformidade_geral_pct: int = Field(..., example=96)

class ItemStatusGraficoDTO(BaseModel):
    status: str = Field(..., example="Conforme") # 'Conforme', 'Atenção', 'Não conforme'
    quantidade: int = Field(..., example=8)
    percentual: float = Field(..., example=66.7)

class StatusGlebasPizzaDTO(BaseModel):
    total: int = Field(..., example=12)
    detalhes: List[ItemStatusGraficoDTO]

class AtividadeAgendadaDTO(BaseModel):
    tipo_atividade: str = Field(..., example="Validação Ambiental")
    descricao: str = Field(..., example="Fazenda Boa Esperança - Gleba 07")
    data_prevista: str = Field(..., example="15/07/2026")

class RespostaStatusAtividadesDTO(BaseModel):
    status_glebas: StatusGlebasPizzaDTO
    proximas_atividades: List[AtividadeAgendadaDTO]
