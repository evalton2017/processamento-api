# app/dto/PlanejamentoAgronomicoDTO.py
from typing import List

from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel
from datetime import date

class PlanejamentoAgronomicoDTO(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    municipio_ibge: int = Field(..., description="Código IBGE")
    cultura: str = Field(..., description="Cultura")
    safra: str = Field(..., description="Safra")
    volume_declarado_comercializar: float = Field(..., description="Volume")

    # CONFIRA ESTAS DUAS EXPRESSÕES ABAIXO (LETRA POR LETRA):
    data_estimada_plantio: date = Field(..., description="Data de Plantio")
    data_estimada_colheita: date = Field(..., description="Data de Colheita")

class JanelaSugerida(BaseModel):
    decendio: int
    periodo_sugerido: str
    risco_pct: int

# Resposta completa esperada pelo formulário Angular
class ZoneamentoZarcResponse(BaseModel):
    cultura: str
    municipio_ibge: int
    data_inicio_permitida: date
    data_fim_permitida: date
    sugestoes_janelas_plantio: List[JanelaSugerida]
    mensagem_auxiliar: str

class ValidarZarcRequest(BaseModel):
    id_gleba: int
    municipio_ibge: int
    cultura: str
    safra: str
    volumeDeclaradoComercializar: float
    dataEstimadaPlantio: date     # Pydantic valida strings YYYY-MM-DD automaticamente
    dataEstimadaColheita: date

# 📦 Contrato de Saída Simplificado (Retorno)
class ValidarZarcSimplificadoResponse(BaseModel):
    status_validacao: str  # "CONFORME" ou "INCONFORME"
    mensagem: str