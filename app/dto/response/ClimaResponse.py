from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime


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

class ClimaResumoResponse(BaseModel):
    chuva_acumulada_mm: float = Field(..., example=654.0)
    variacao_chuva_pct: float = Field(..., example=-8.0)
    temp_media_celsius: float = Field(..., example=24.8)
    variacao_temp_celsius: float = Field(..., example=0.6)
    dias_sem_chuva: int = Field(..., example=126)
    variacao_dias_sem_chuva: float = Field(..., example=16.0)
    vel_vento_kmh: float = Field(..., example=12.4)
    variacao_vel_vento: float = Field(..., example=-1.2)

class ClimaResumoEstadoDTO(BaseModel):
    uf: str = Field(..., example="GO")
    chuva_acumulada_mm: float = Field(..., example=654.0)
    variacao_chuva_pct: float = Field(..., example=-8.0)
    temp_media_celsius: float = Field(..., example=24.8)
    variacao_temp_celsius: float = Field(..., example=0.6)
    dias_sem_chuva: int = Field(..., example=126)
    variacao_dias_sem_chuva: float = Field(..., example=16.0)
    vel_vento_kmh: float = Field(..., example=12.4)
    variacao_vel_vento: float = Field(..., example=-1.2)

class ValidarZarcRequest(BaseModel):
    id_gleba: int
    municipio_ibge: int
    cultura: str
    safra: str
    volumeDeclaradoComercializar: float
    dataEstimadaPlantio: datetime
    dataEstimadaColheita: datetime

class ValidarZarcSimplificadoResponse(BaseModel):
    status_validacao: str
    mensagem: str

class CulturaZarcResponse(BaseModel):
    id: int = Field(
        ...,
        description="ID único identificador do primeiro registro encontrado para a cultura",
        example=1
    )
    codigo: str = Field(
        ...,
        description="Código abreviado de 3 letras da cultura agrícola",
        example="SOJ"
    )
    nome: str = Field(
        ...,
        description="Nome formatado e capitalizado da cultura homologada no ZARC",
        example="Soja"
    )
    grupo: str = Field(
        ...,
        description="Grupo regulatório de enquadramento da cultura",
        example="GRÃOS"
    )
    ativo: bool = Field(
        ...,
        description="Status de ativação para monitoramento e conformidade",
        example=True
    )
    permite_zarc: bool = Field(
        ...,
        description="Sinalizador de conformidade estrita com as janelas climáticas oficiais",
        example=True
    )
    data_cadastro: Optional[str] = Field(
        None,
        description="Data da última atualização ou inclusão do zoneamento no banco geográfico",
        example="2026-06-21"
    )

    # Configuração para o Pydantic ler as propriedades diretamente dos objetos Row do SQLAlchemy
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 45,
                "codigo": "MIL",
                "nome": "Milho",
                "grupo": "GRÃOS",
                "ativo": True,
                "permite_zarc": True,
                "data_cadastro": "2026-06-21"
            }
        }
    }
