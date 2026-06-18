from pydantic import BaseModel, Field
from typing import Dict, Any

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
