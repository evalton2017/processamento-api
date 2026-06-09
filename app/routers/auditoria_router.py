from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List
from app.services.validacao_service import calcular_assertividade_anexo_vi

router = APIRouter(prefix="/api/v1/secretaria", tags=["Auditoria e Testes Semestrais"])

class RequisicaoTesteSemestral(BaseModel):
    id_ciclo_auditoria: int
    culturas_reais_campo: List[str] = Field(..., example=["SOJA", "MILHO", "SOJA", "PASTAGEM"])
    culturas_preditas_ia: List[str] = Field(..., example=["SOJA", "MILHO", "MILHO", "PASTAGEM"])

@router.post("/validar-assertividade-anexo-vi", status_code=status.HTTP_200_OK)
async def validar_indicadores_assertividade(dados: RequisicaoTesteSemestral):
    """
    Interface para a Secretaria de Inovação submeter testes semestrais
    e validar as métricas da fórmula do Anexo VI.
    """
    try:
        resultado_laudo = calcular_assertividade_anexo_vi(
            culturas_reais=dados.culturas_reais_campo,
            culturas_preditas=dados.culturas_preditas_ia
        )

        # Injeta metadados da auditoria
        resultado_laudo["id_ciclo_auditoria"] = dados.id_ciclo_auditoria
        return resultado_laudo

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro no cálculo do Anexo VI: {str(e)}")
