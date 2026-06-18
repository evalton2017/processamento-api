import logging
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from app.database.session import get_async_db
from app.dto.produtor.dashboard_produtor_schema import RespostaDashboardProdutorDTO, RespostaConformidadeAmbientalDTO, \
    RespostaStatusAtividadesDTO
from app.services.produtor.dashboard_produtor_service import DashboardProdutorService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/dashboard-produtor",
    tags=["Dashboard Produtor"]
)

@router.get("/resumo", status_code=status.HTTP_200_OK, response_model=RespostaDashboardProdutorDTO)
async def obter_resumo_dashboard_produtor(
        id_produtor: int = Query(..., alias="idProdutor", description="ID identificador do produtor."),
        safra: str = Query("2025/2026", description="Safra alvo selecionada."),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna o payload consolidado de auditoria e monitoramento do produtor
    para renderização dos cards estatísticos em conformidade com o ecossistema ledger.
    """
    logger.info(f"Processando requisição HTTP get do dashboard_produtor para id: {id_produtor}.")
    try:
        service = DashboardProdutorService(db)
        return await service.obter_dados_dashboard_produtor(id_produtor=id_produtor, safra=safra)

    except Exception as e:
        logger.error(f"Erro ao processar roteamento do dashboard_produtor: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro no servidor ao buscar dados consolidados do produtor."
        )

@router.get("/conformidade-ambiental", status_code=status.HTTP_200_OK, response_model=RespostaConformidadeAmbientalDTO)
async def obter_resumo_conformidade_ambiental(
        id_produtor: int = Query(..., alias="idProdutor", description="ID do produtor logado."),
        safra: str = Query("2025/2026", description="Safra selecionada no combo superior."),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna o demonstrativo de conformidade socioambiental detalhado por critério,
    extraído diretamente das assinaturas do Ledger para montagem da tabela do produtor.
    """
    logger.info(f"Processando GET /conformidade-ambiental para o produtor {id_produtor} na safra {safra}.")
    try:
        service = DashboardProdutorService(db)
        return await service.obter_tabela_conformidade_ambiental(id_produtor=id_produtor, safra=safra)
    except Exception as e:
        logger.error(f"Erro ao compilar tabela de conformidade do produtor: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no servidor ao estruturar a matriz de conformidade."
        )

@router.get("/status-atividades", status_code=status.HTTP_200_OK, response_model=RespostaStatusAtividadesDTO)
async def obter_status_e_proximas_atividades_dashboard(
        id_produtor: int = Query(..., alias="idProdutor", description="ID do produtor logado."),
        safra: str = Query("2025/2026", description="Safra selecionada."),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna o agrupamento estatístico de status das glebas para o gráfico de pizza (Donut Chart)
    e a listagem cronológica preditiva das próximas checagens contínuas da esteira VMG.
    """
    logger.info(f"Acessando GET /status-atividades para o produtor {id_produtor} na safra {safra}.")
    try:
        service = DashboardProdutorService(db)
        return await service.obter_status_e_proximas_atividades(id_produtor=id_produtor, safra=safra)
    except Exception as e:
        logger.error(f"Erro ao compilar bloco de status e atividades do produtor: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no servidor ao estruturar o painel de atividades."
        )