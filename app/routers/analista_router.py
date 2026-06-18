import logging
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional

from app.database.session import get_async_db
from app.dto.analista.filtro_analista_gleba import RespostaTabelaGlebasNovaDTO
from app.services.analista.analista_service import AnalistaService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/analista",
    tags=["Analista - Consulta Avançada"]
)

@router.get("/glebas/filtrar", status_code=status.HTTP_200_OK, response_model=RespostaTabelaGlebasNovaDTO)
async def listar_glebas_novo_modelo(
        safra: str = Query(..., description="Ano da safra alvo. Exemplo: '2025/2026'"),
        municipio: str = Query("Todos", description="Filtro por nome do município ou 'Todos'"),
        cultura: str = Query("Todos", description="Filtro por cultura (Ex: 'Soja', 'Milho') ou 'Todos'"),
        status_gleba: str = Query("Todos", alias="statusGleba", description="Status operacional da gleba"),
        conformidade_ambiental: str = Query("Todos", alias="conformidadeAmbiental", description="Status de conformidade ambiental"),
        cpf_cnpj: Optional[str] = Query(None, alias="cpfCnpj", description="Filtrar por CPF ou CNPJ do produtor rural"),
        car: Optional[str] = Query(None, description="Filtrar por código ou parte do código CAR"),
        ordenar_por: str = Query("Mais recentes", alias="ordenarPor", description="Critério de ordenação da tabela"),
        pagina: int = Query(1, ge=1, description="Número da página atual para paginação"),
        limite: int = Query(8, ge=1, description="Quantidade de registros retornados por página"),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna a listagem de glebas monitoradas filtrada, estruturada e paginada
    conforme as colunas e filtros exatos da tela de gerenciamento do Analista.
    """
    logger.info(
        f"Iniciando busca avançada de glebas para a safra {safra}. "
        f"Filtros - Estado/Mun: {municipio}, Conf. Ambiental: {conformidade_ambiental}"
    )

    try:
        # Montagem do dicionário de filtros estruturado para repassar ao Service
        filtros = {
            "safra": safra,
            "municipio": municipio,
            "cultura": cultura,
            "status_gleba": status_gleba,
            "conformidade_ambiental": conformidade_ambiental,
            "cpf_cnpj": cpf_cnpj,
            "car": car,
            "ordenar_por": ordenar_por
        }

        # Instanciação direta do serviço com a sessão injetada do banco de dados
        service = AnalistaService(db)

        # Orquestra a regra de negócio e retorna o DTO plano estruturado
        resultado = await service.buscar_listagem_novo_modelo(
            filtros=filtros,
            page=pagina,
            limit=limite
        )

        logger.info(f"Busca realizada com sucesso. Total de registros encontrados: {resultado.get('total_registros')}")
        return resultado

    except ValueError as val_err:
        logger.warning(f"Erro de validação nos parâmetros fornecidos pelo analista: {str(val_err)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parâmetros de consulta inválidos: {str(val_err)}"
        )
    except Exception as e:
        logger.error(f"Erro crítico não tratado ao filtrar listagem do analista: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no servidor ao processar a consulta avançada de glebas."
        )
