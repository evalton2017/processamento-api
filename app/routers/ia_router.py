from fastapi import APIRouter, status, HTTPException
from pydantic import BaseModel
from celery.result import AsyncResult

from app.services.ia_pipeline import executar_classificacao_ia_vmg, celery_app

router = APIRouter(prefix="/api/v1/ia", tags=["Módulo de Inteligência Artificial"])

class RequisicaoAnaliseIA(BaseModel):
    id_gleba: int
    cultura_declarada: str

@router.post("/classificar", status_code=status.HTTP_202_ACCEPTED)
async def solicitar_classificacao_ia(dados: RequisicaoAnaliseIA):
    try:
        # Removido o argumento 'app=celery_app' de dentro do apply_async,
        # a task já reconhece o próprio app automaticamente.
        task = executar_classificacao_ia_vmg.apply_async(
            args=[dados.id_gleba, dados.cultura_declarada]
        )

        return {
            "mensagem": "Pipeline de classificação de culturas por IA iniciado.",
            "task_id": task.id,
            "status": "PROCESSANDO",
            "url_checagem_status": f"/api/v1/ia/status/{task.id}"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao enfileirar processo de IA: {str(e)}"
        )

@router.get("/status/{task_id}")
async def obter_status_pipeline_ia(task_id: str):
    """
    Consulta o estado de execução da tarefa de IA na fila do Redis.
    """
    # Força a checagem a ler o backend local do Redis do Windows, evitando o erro de timeout
    res = AsyncResult(task_id, app=celery_app)

    if res.state == 'PENDING':
        return {"task_id": task_id, "status": "AGUARDANDO_WORKER"}
    elif res.state == 'SUCCESS':
        return {"task_id": task_id, "status": "SUCESSO", "resultado": res.result}
    elif res.state == 'FAILURE':
        return {"task_id": task_id, "status": "FALHA", "erro": str(res.info)}

    return {"task_id": task_id, "status": res.state}
