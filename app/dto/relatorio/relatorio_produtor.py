# app/dto/response/atestado_response import AtestadoDetalhadoResponse
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List

class CardGlebaDTO(BaseModel):
    nome_gleba: str
    cultura_principal: str
    safra: str
    periodo_analisado: str
    status_atestado: str
    data_emissao_atestado: datetime
    area_hectares: float

class ResumoConformidadeDTO(BaseModel):
    ambiental_conforme: bool
    agricola_conforme: bool
    boas_praticas_conforme: bool
    zarc_conforme: bool
    produtividade_conforme: bool
    produtividade_estimada_sacas: float
    produtividade_declarada_sacas: float

class InformacoesGlebaDTO(BaseModel):
    municipio_uf: str
    codigo_car: str
    coordenadas_centroide: str
    data_cadastro: datetime

class EventoLinhaTempoDTO(BaseModel):
    fase: str
    data_evento: date
    tipo: str  # 'Estimado' ou 'Realizado'

class MetricasProdutividadeDTO(BaseModel):
    declarado_sacas_ha: float
    estimado_ia_sacas_ha: float
    referencia_regional_sacas_ha: float

class DadosAtestadoDTO(BaseModel):
    codigo_atestado: str
    orgao_emissor: str
    metodo_validacao: str
    validade_inicio: datetime
    validade_fim: datetime
    hash_documento_blockchain: str

class AtestadoDetalhadoResponse(BaseModel):
    cabecalho: CardGlebaDTO
    conformidade: ResumoConformidadeDTO
    informacoes_gerais: InformacoesGlebaDTO
    linha_tempo_safra: List[EventoLinhaTempoDTO]
    produtividade: MetricasProdutividadeDTO
    metadados_atestado: DadosAtestadoDTO
