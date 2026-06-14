from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from sqlalchemy import select

from app.database.session import get_db
from app.models.classificacao_model import ClassificacoesCulturas
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard Analytics"]
)

@router.get("/consolidado", status_code=status.HTTP_200_OK)
async def obter_dashboard_completo(
        safra: str = Query(..., description="Ano da safra alvo. Exemplo: '2023/2024' ou '2024'"),
        estado: str = Query("Todos", description="Filtro por sigla do estado (Ex: 'MT', 'SP') ou 'Todos'"),
        db: AsyncSession = Depends(get_db)  # 🛠️ Tipagem assíncrona
) -> Dict[str, Any]:
    """
    Retorna todos os dados consolidados da tela inicial do Dashboard em uma única requisição.

    Traz os blocos de KPIs, dados do gráfico de culturas, gráfico de estados,
    status de criticidade por região geográfica e o feed de notificações recentes.
    """
    service = DashboardService(db)
    resposta = await service.obter_dados_dashboard(safra=safra, estado=estado)

    if not resposta.get("sucesso"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=resposta.get("mensagem", "Erro interno ao processar dados do dashboard.")
        )

    return resposta


@router.get("/kpis", status_code=status.HTTP_200_OK)
async def obter_apenas_kpis(
        safra: str = Query(..., description="Ano da safra alvo."),
        estado: str = Query("Todos", description="Filtrar por UF ou 'Todos'"),
        db: AsyncSession = Depends(get_db)  # 🛠️ Tipagem assíncrona
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
        db: AsyncSession = Depends(get_db)  # 🛠️ Tipagem assíncrona
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
        db: AsyncSession = Depends(get_db)  # 🛠️ Tipagem assíncrona
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
async def obter_status_mapa(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:  # 🛠️ Tipagem assíncrona
    """
    Retorna o nível de risco/criticidade de cada estado ('Alerta', 'Atenção', 'Normal')
    baseado no volume de notificações ativas para colorir o mapa do Frontend.
    """
    service = DashboardService(db)
    resposta = await service.obter_alertas_mapa()

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta


@router.get("/eventos/recentes", status_code=status.HTTP_200_OK)
async def obter_feed_eventos(
        limite: int = Query(5, ge=1, le=50, description="Quantidade de registros retornados no feed"),
        db: AsyncSession = Depends(get_db)  # 🛠️ Tipagem assíncrona
) -> Dict[str, Any]:
    """
    Retorna a lista das últimas notificações e ocorrências geradas no sistema (Feed de Auditoria).
    """
    service = DashboardService(db)
    resposta = await service.obter_ultimos_eventos(limite=limite)

    if not resposta.get("sucesso"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resposta.get("mensagem"))
    return resposta
@router.get("/filtros-agricolas", status_code=status.HTTP_200_OK)
async def obter_filtros_agricolas_wizard(
        db_principal: AsyncSession = Depends(get_db)
):
    """
    Retorna listas únicas de safras e culturas extraídas das
    classificações para alimentar os dropdowns do planejamento agronômico.
    """
    try:
        async with db_principal.begin():
            # 1. Busca safras distintas cadastradas no sistema
            stmt_safras = select(ClassificacoesCulturas.safra).distinct().order_by(ClassificacoesCulturas.safra.desc())
            exec_safras = await db_principal.execute(stmt_safras)
            safras = exec_safras.scalars().all()

            # 2. Busca culturas preditas distintas cadastradas no sistema
            stmt_culturas = select(ClassificacoesCulturas.cultura_predita).distinct().order_by(ClassificacoesCulturas.cultura_predita.asc())
            exec_culturas = await db_principal.execute(stmt_culturas)
            culturas = exec_culturas.scalars().all()

            # Fallbacks estáticos caso o seu banco de dados esteja inicialmente vazio/zerado em homologação
            lista_safras = list(safras) if safras else ["2024/2025", "2025/2026", "2026/2027"]
            lista_culturas = list(culturas) if culturas else ["Soja", "Milho", "Algodão", "Feijão"]

            return {
                "safras": lista_safras,
                "culturas": lista_culturas
            }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar catálogo de parâmetros agrícolas: {str(e)}"
        )