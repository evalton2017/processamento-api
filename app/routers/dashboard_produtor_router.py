import logging
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from app.database.session import get_async_db
from app.dto.produtor.dashboard_produtor_schema import RespostaDashboardProdutorDTO
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
