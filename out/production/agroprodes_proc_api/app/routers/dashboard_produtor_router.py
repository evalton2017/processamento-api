import io
import logging
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional

from starlette.responses import StreamingResponse

from app.database.session import get_async_db
from app.dto.produtor.dashboard_produtor_schema import RespostaDashboardProdutorDTO, RespostaConformidadeAmbientalDTO, \
    RespostaStatusAtividadesDTO, ProdutividadeEstimadaResponse, ClimaResumoResponse
from app.services.mapa.raster_tile import RasterService
from app.services.produtor.dashboard_produtor_service import DashboardProdutorService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/dashboard-produtor",
    tags=["Dashboard Produtor"]
)

@router.get("/resumo", status_code=status.HTTP_200_OK, response_model=RespostaDashboardProdutorDTO)
async def obter_resumo_dashboard_produtor(
        id_produtor: int = Query(..., alias="id_produtor", description="ID identificador do produtor."),
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
        id_produtor: int = Query(..., alias="id_produtor", description="ID do produtor logado."),
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
        id_produtor: int = Query(..., alias="id_produtor", description="ID do produtor logado."),
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

@router.get("/produtividade-estimada", response_model=ProdutividadeEstimadaResponse, status_code=status.HTTP_200_OK)
async def obter_produtividade_estimada_ia(
        id_produtor: int,
        safra: Optional[str] = "2025/2026",
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Retorna os dados consolidados de produtividade calculados por IA (Média sc/ha,
    volume de sacas, área total e evolução mensal) para alimentar o gráfico do painel.
    """
    service = DashboardProdutorService(db_principal)
    return await service.calcular_produtividade_estimada(id_produtor, safra)


@router.get("/resumo-climatico", response_model=ClimaResumoResponse, status_code=status.HTTP_200_OK)
async def obter_resumo_climatico_regiao(
        id_produtor: int,
        dias: Optional[int] = 60,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Retorna o resumo climatológico dos últimos 60 dias (Precipitação, Temperatura,
    Estiagem e Vento) calculado por interpolação a partir das estações do INMET próximas.
    """
    service = DashboardProdutorService(db_principal)
    return await service.obter_resumo_climatico_regiao(id_produtor, dias)

@router.get("/analise-ambiental/raster/{id_raster}/download", status_code=status.HTTP_200_OK)
async def baixar_raster_geotiff_novo(
        id_raster: int,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Endpoint atualizado que consome a nova tabela 'metadados_raster' via pipeline streaming.
    """
    service = RasterService(db_principal)

    # 1. Obtém a URL externa e o nome padronizado do banco
    url_origem, nome_arquivo = await service.obter_metadados_e_stream_url(id_raster)

    # 2. Retorna a resposta em modo streaming repassando o gerador binário do HTTPX
    return StreamingResponse(
        service.stream_geotiff_remoto(url_origem),
        media_type="image/tiff",
        headers={
            "Content-Disposition": f"attachment; filename={nome_arquivo}",
            "Cache-Control": "no-cache"
        }
    )