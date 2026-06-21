import logging
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional

from app.database.session import get_async_db
from app.dto.response.ClimaResponse import ClimaResumoEstadoDTO
from app.dto.response.eventos_climaticos_response import EventoClimaticoResponse
from app.dto.response.ultimos_atestados_response import UltimosAtestadosResponse
from app.services.analista.dashboard_service import DashboardService
from app.services.produtor.dashboard_produtor_service import DashboardProdutorService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard Analytics"]
)


@router.get("/consolidado", status_code=status.HTTP_200_OK)
async def obter_dashboard_completo(
        safra: str = Query(..., description="Ano da safra alvo. Exemplo: '2023/2024' ou '2024'"),
        estado: str = Query("Todos", description="Filtro por sigla do estado (Ex: 'MT', 'SP') ou 'Todos'"),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna estritamente as propriedades de KPIs planos calculadas da base,
    entregando o formato exato exigido pela interface DashboardKpis do Frontend.
    """
    service = DashboardService(db)
    # Retorna o dicionário de KPIs diretamente para a raiz da resposta HTTP
    return await service.obter_dados_dashboard(safra=safra, estado=estado)


@router.get("/kpis", status_code=status.HTTP_200_OK)
async def obter_apenas_kpis(
        safra: str = Query(..., description="Ano da safra alvo."),
        estado: str = Query("Todos", description="Filtrar por UF ou 'Todos'"),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna estritamente os indicadores numéricos do topo (Contratos, Glebas, Área, Alertas e Atestados).
    Útil para atualizações rápidas ou cliques de filtros na tela.
    """
    service = DashboardService(db)
    resposta = await service.obter_kpis_topo(safra=safra, estado=estado)

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta


@router.get("/grafico/culturas", status_code=status.HTTP_200_OK)
async def obter_grafico_culturas(
        safra: str = Query(..., description="Ano da safra alvo."),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna os dados de distribuição e percentual por tipo de cultura predita (Gráfico de Rosca/Pizza).
    """
    service = DashboardService(db)
    resposta = await service.obter_distribuicao_culturas(safra=safra)

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta


@router.get("/grafico/estados", status_code=status.HTTP_200_OK)
async def obter_grafico_estados(
        safra: str = Query(..., description="Ano da safra alvo."),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna a volumetria de contratos distribuídos regionalmente por estado (Gráfico de Barras).
    """
    service = DashboardService(db)
    resposta = await service.obter_distribuicao_estados(safra=safra)

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta


@router.get("/mapa/status", status_code=status.HTTP_200_OK)
async def obter_status_mapa(db: AsyncSession = Depends(get_async_db)) -> Dict[str, Any]:
    """
    Retorna o nível de risco/criticidade de cada estado ('Alerta', 'Atenção', 'Normal')
    baseado no volume de notificações ativas para colorir o mapa do Frontend.
    """
    service = DashboardService(db)
    resposta = await service.obter_alertas_mapa()

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta


@router.get(
    "/ultimos-atestados",
    response_model=List[UltimosAtestadosResponse],
    status_code=status.HTTP_200_OK
)
async def listar_ultimos_atestados_emitidos(
        db: AsyncSession = Depends(get_async_db)
):
    """
    Retorna os últimos atestados de conformidade agrícola emitidos pelo
    Ledger imutável para renderização da segunda tabela do painel.
    """
    try:
        service = DashboardService(db)

        return await service.obter_eventos_climaticos_recentes()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao compilar os atestados emitidos pelo ledger: {str(e)}"
        )

# ==========================================
# 🚀 NOVOS ENDPOINTS DO DASHBOARD
# ==========================================

@router.get("/alertas", status_code=status.HTTP_200_OK, response_model=List[Dict[str, Any]])
async def obter_alertas_dashboard(
        db: AsyncSession = Depends(get_async_db)
) -> List[Dict[str, Any]]:
    """
    Retorna a volumetria consolidada e agrupada por tipo de alerta.
    Exemplo de saída: [{'tipo_alerta': 'Fora do ZARC', 'quantidade': 52}, ...]
    """
    service = DashboardService(db)
    resposta = await service.obter_alertas_agrupados()

    if not resposta.get("sucesso"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=resposta.get("mensagem", "Erro ao buscar dados de alertas.")
        )
    return resposta.get("dados", [])


@router.get("/atestados", status_code=status.HTTP_200_OK, response_model=List[Dict[str, Any]])
async def obter_atestados_dashboard(
        db: AsyncSession = Depends(get_async_db)
) -> List[Dict[str, Any]]:
    """
    Lista detalhada de atestados/certificados emitidos vinculando
    as tabelas de gleba, produtor e município.
    """
    service = DashboardService(db)
    resposta = await service.obter_lista_atestados()

    if not resposta.get("sucesso"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=resposta.get("mensagem", "Erro ao processar listagem de atestados.")
        )
    return resposta.get("dados", [])


@router.get("/heatmap", status_code=status.HTTP_200_OK, response_model=List[Dict[str, Any]])
async def obter_dados_heatmap(
        db: AsyncSession = Depends(get_async_db)
) -> List[Dict[str, Any]]:
    """
    Retorna pontos do mapa contendo coordenadas geográficas e status de
    criticidade (verde, vermelho) para renderização do mapa de calor.
    """
    service = DashboardService(db)
    resposta = await service.obter_pontos_heatmap()

    if not resposta.get("sucesso"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=resposta.get("mensagem", "Erro ao coletar pontos para o heatmap.")
        )
    return resposta.get("dados", [])

@router.get("/timeline/{id_gleba}", status_code=status.HTTP_200_OK)
async def obter_timeline_gleba(
        id_gleba: int,
        db: AsyncSession = Depends(get_async_db)
) -> List[Dict[str, Any]]:
    """
    Retorna a rastreabilidade histórica e imutável de auditoria de uma gleba específica.
    """
    service = DashboardService(db)
    resposta = await service.obter_timeline_vmg(id_gleba=id_gleba)

    if not resposta.get("sucesso"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resposta.get("mensagem", "Erro ao processar linha do tempo da auditoria.")
        )
    return resposta.get("dados", [])

@router.get("/analise-ambiental", status_code=status.HTTP_200_OK)
async def obter_ia_analise_ambiental(
        safra: str = Query(..., description="Ano da safra alvo."),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna a volumetria de conformidade ambiental delegando o fluxo ao Service.
    """
    service = DashboardService(db)
    resposta = await service.obter_ia_analise_ambiental(safra=safra)

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta.get("dados", {})


@router.get("/ia-classificacao", status_code=status.HTTP_200_OK)
async def obter_ia_classificacao_culturas(
        safra: str = Query(..., description="Ano da safra alvo."),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna a acurácia média e a distribuição percentual das culturas preditas por IA via Service.
    """
    service = DashboardService(db)
    resposta = await service.obter_ia_classificacao_culturas(safra=safra)

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta.get("dados", {})


@router.get("/produtividade-estimada", status_code=status.HTTP_200_OK)
async def obter_ia_produtividade_estimada(
        safra: str = Query(..., description="Ano da safra alvo."),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna a média geral de sacas/ha, área e volume produtivo calculado pela IA via Service.
    """
    service = DashboardService(db)
    resposta = await service.obter_ia_produtividade_estimada(safra=safra)

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta.get("dados", {})


@router.get("/resumo-climatico", response_model=List[ClimaResumoEstadoDTO], status_code=status.HTTP_200_OK)
async def obter_resumo_meteorologico_inmet(
        dias: int = 60,
        uf: Optional[str] = Query(None, description="Filtro opcional por sigla do Estado (Ex: GO, MG, Todos)"),
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Endpoint macro-regional: Retorna o balanço de séries climáticas do INMET por Estado (UF),
    permitindo filtragem opcional ou consolidação global de todas as bases.
    """
    service = DashboardService(db_principal)
    return await service.obter_resumo_climatico_global_ou_estado(dias=dias, uf=uf)

@router.get(
    "/eventos-climaticos",
    response_model=List[EventoClimaticoResponse],
    status_code=status.HTTP_200_OK
)
async def listar_eventos_climaticos_recentes(
        db: AsyncSession = Depends(get_async_db)
):
    """
    Retorna a consolidação histórica total dos eventos climáticos e alertas emitidos
    nos últimos 60 meses exigidos pela portaria regulatória para a tabela do dashboard.
    """
    try:
        service = DashboardService(db)
        return await service.obter_eventos_climaticos_recentes()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao compilar os dados da série histórica climática de 60 meses: {str(e)}"
        )