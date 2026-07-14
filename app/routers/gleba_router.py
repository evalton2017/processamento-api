# app/routers/produtor_router.py
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_async_db
from app.dto.response.gleba_response import RespostaLaudoDetalhadoGleba
from app.services.gleba_service import GlebaService

# O grupo possui o prefixo prefix="/api/v1/gleba"
router = APIRouter(prefix="/api/v1/gleba", tags=["Glebas"])

@router.get("/{id_gleba}/laudo-detalhado", response_model=RespostaLaudoDetalhadoGleba, status_code=status.HTTP_200_OK)
async def obter_laudo_detalhado_analise_vmg(
        id_gleba: int,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Endpoint Unificado: Alimenta de uma única vez a esteira horizontal,
    o painel de pendências e as caixas de informações do ZARC do dashboard analítico.
    """
    service = GlebaService(db_principal)
    resultado = await service.obter_detalhe_laudo_completo(id_gleba)

    if not resultado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Laudo analítico não localizado para a gleba {id_gleba}."
        )
    return resultado