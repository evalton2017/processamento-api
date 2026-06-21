# app/routers/produtor_router.py
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_async_db
from app.dto.response.gleba_response import RespostaLaudoDetalhadoGleba
from app.services.gleba_service import GlebaService

# O grupo possui o prefixo prefix="/api/v1/gleba"
router = APIRouter(prefix="/api/v1/gleba", tags=["Glebas"])

@router.get("/{id_gleba}/laudo-detalhado", response_model=RespostaLaudoDetalhadoGleba, status_code=status.HTTP_200_OK)
async def obter_laudo_detalhado_gleba_auditada(
        id_gleba: int,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Retorna o detalhamento completo do laudo imutável da esteira de análises VMG,
    alimentando o componente inferior do mapa e as timelines de atividades.
    """
    service = GlebaService(db_principal)
    resultado = await service.obter_detalhe_laudo_completo(id_gleba)

    if not resultado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhum laudo ou registro localizado para a gleba informada: {id_gleba}."
        )

    return resultado
