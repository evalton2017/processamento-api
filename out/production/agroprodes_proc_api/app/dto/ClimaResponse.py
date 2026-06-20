from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

# --- MODELOS DE ENTRADA (REQUEST SCHEMAS) ---

class RequisicaoAnaliseClimatica(BaseModel):
    id_gleba: int = Field(..., description="ID identificador do talhão/gleba no banco de dados.")
    cultura: str = Field(..., example="SOJA", description="Nome da cultura para calibração de limiares agronômicos.")


# --- MODELOS DE SAÍDA (RESPONSE SCHEMAS) ---

class MetadadosSolicitacao(BaseModel):
    latitude_centroide: float = Field(..., example=-15.7938)
    longitude_centroide: float = Field(..., example=-47.8827)
    janela_meses: int = Field(60, description="Período histórico obrigatório pelo termo de referência.")
    periodo_analisado: str = Field(..., example="2021-06-09 ate 2026-06-09")

class IndicadoresAcumulados(BaseModel):
    total_dias_sem_chuva: int = Field(..., description="Quantidade total de dias sem chuva durante o período monitorado.")
    dias_com_chuvas_excessivas: int = Field(..., description="Dias com chuvas acima do teto tolerado pela cultura.")
    dias_com_chuvas_insuficientes: int = Field(..., description="Dias com precipitação abaixo do limiar mínimo de absorção.")
    maxima_sequencia_dias_secos: int = Field(..., description="Maior sequência contínua de dias em veranico.")

class AlertaClimatico(BaseModel):
    evento: str = Field(..., example="ESTRESSE_HIDRICO_SEVERO (VERANICO)")
    descricao: str = Field(..., example="Detectado período contínuo de 20 dias sem chuva na gleba.")

class RespostaClimaticaHistorica(BaseModel):
    """
    Modelo de dados final de resposta exigido para auditorias do MAPA e dashboards.
    """
    id_gleba: int
    metadados_solicitacao: MetadadosSolicitacao
    indicadores_acumulados: IndicadoresAcumulados
    alertas_emitidos: List[AlertaClimatico] = Field(default=[], description="Lista de anomalias meteorológicas severas detectadas.")
