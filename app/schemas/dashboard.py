from pydantic import BaseModel, Field
from typing import List

# ==========================================
# 1. SCHEMAS PARA OS FILTROS DO TOPO
# ==========================================

class FiltrosDashboardResponse(BaseModel):
    safras: List[str] = Field(..., description="Lista de safras disponíveis, ex: ['Safra 2025', 'Safra 2026']")
    estados: List[str] = Field(..., description="Lista de siglas de estados disponíveis, ex: ['MT', 'BA', 'GO']")


# ==========================================
# 2. SCHEMAS PARA OS CARDS DE METRICAS (KPIs)
# ==========================================

class MetricaKpiItem(BaseModel):
    valor_atual: float = Field(..., description="O valor consolidado atual da métrica")
    variacao_percentual: float = Field(..., description="Variação percentual comparada à safra anterior (pode ser negativa)")
    sufixo: str = Field("", description="Sufixo visual do valor. Ex: 'ha' para hectares, ou vazio para contagens ordinárias")

class DashboardKpisResponse(BaseModel):
    contratos: MetricaKpiItem
    glebas_monitoradas: MetricaKpiItem
    area_total: MetricaKpiItem
    alertas_ativos: MetricaKpiItem
    atestados_emitidos: MetricaKpiItem


# ==========================================
# 3. SCHEMAS PARA OS GRAFICOS e MAPA
# ==========================================

class ContratosPorEstadoItem(BaseModel):
    estado: str = Field(..., description="Sigla do estado (UF). Ex: 'MT'")
    quantidade: int = Field(..., description="Quantidade total de contratos naquele estado")

class StatusEstadoItem(BaseModel):
    estado: str = Field(..., description="Sigla do estado (UF). Ex: 'BA'")
    status: str = Field(..., description="Classificação de risco para pintar o mapa: 'Normal', 'Atenção' ou 'Alerta'")

class ContratosPorCulturaItem(BaseModel):
    cultura: str = Field(..., description="Nome da cultura. Ex: 'Soja', 'Milho'")
    quantidade: int = Field(..., description="Quantidade absoluta de contratos")
    percentual: float = Field(..., description="Percentual representativo no gráfico de rosca. Ex: 65.0")


# ==========================================
# 4. SCHEMA PARA O FEED DE EVENTOS RECENTES
# ==========================================

class EventoRecenteItem(BaseModel):
    id: int
    descricao: str = Field(..., description="Texto do evento. Ex: 'Novo classificação IA concluída'")
    data_hora: str = Field(..., description="Data e hora formatada do evento. Ex: '13/06/2026 08:30'")
    status: str = Field(..., description="Tag de criticidade visual: 'Sucesso', 'Alerta' ou 'Atenção'")


# ==========================================
# 5. SCHEMA AGREGADOR (VISAO GERAL)
# ==========================================

class DashboardVisaoGeralResponse(BaseModel):
    """
    Schema unificado que entrega todos os dados da tela em uma única chamada de API (Melhor prática)
    """
    kpis: DashboardKpisResponse
    grafico_barras_estados: List[ContratosPorEstadoItem]
    mapa_status_estados: List[StatusEstadoItem]
    grafico_rosca_culturas: List[ContratosPorCulturaItem]
    total_contratos_cultura: int = Field(..., description="O número central exibido na rosca (12.854)")
    eventos_recentes: List[EventoRecenteItem]

    class Config:
        from_attributes = True  # Permite que o Pydantic leia diretamente os modelos do seu ORM (SQLAlchemy)
