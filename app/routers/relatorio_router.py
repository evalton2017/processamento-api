# app/routers/relatorio_router.py
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_async_db
from app.dto.relatorio.relatorio_produtor import AtestadoDetalhadoResponse
from app.services.relatorio.relatorio_service import RelatorioService
from fastapi.responses import Response

router = APIRouter(prefix="/api/v1/relatorio", tags=["Relatórios & Atestados"])

@router.get("/gleba/{id_gleba}/atestado-detalhes", response_model=AtestadoDetalhadoResponse, status_code=status.HTTP_200_OK)
async def obter_detalhes_atestado_por_id_da_gleba(
        id_gleba: int,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Endpoint de Auditoria VMG:
    Retorna o relatório analítico compilado com base no ID da Gleba especificado,
    buscando a última emissão válida gravada no esquema imutável do sistema.
    """
    service = RelatorioService(db_principal)
    resultado = await service.gerar_relatorio_tela_atestado_por_gleba(id_gleba)

    if not resultado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gleba código {id_gleba} não foi encontrada na base transacional agroprods."
        )
    return resultado

@router.get("/gleba/{id_gleba}/exportar-pdf", response_class=Response)
async def exportar_atestado_vmg_pdf(
        id_gleba: int,
        db: AsyncSession = Depends(get_async_db)
):
    service = RelatorioService(db)
    pdf_binario = await service.gerar_pdf_oficial_vmg(id_gleba)

    if not pdf_binario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Não foi possível gerar o PDF para a gleba informada."
        )

    # Retorna o arquivo diretamente como um anexo para o navegador baixar nativamente
    return Response(
        content=pdf_binario,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Atestado_VMG_Gleba_{id_gleba}.pdf"}
    )