import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, status, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import app.database.schemas as schema
from app.database.gleba_model import ClassificacaoCultura, DocumentoTecnico
from app.database.session import get_db

# IMPORTAÇÃO DO TASKIQ
from app.services.celery.celery_task import executar_pipeline, broker

router = APIRouter(prefix="/api/v1/ia", tags=["IA Pipeline"])

UPLOAD_DIR = "./armazenamento_documentos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ----------------------------
# MODELS
# ----------------------------
class PayloadSalvarIA(BaseModel):
    gleba_id: int
    safra: str
    cultura_predita: str
    cultura_real: Optional[str]
    confianca_ia: float


class RequisicaoAnaliseIA(BaseModel):
    id_gleba: int
    id_produtor: int
    cultura_declarada: str


# ----------------------------
# 1. DISPARAR PIPELINE (AJUSTADO PARA TASKIQ)
# ----------------------------
@router.post("/classificar", status_code=status.HTTP_202_ACCEPTED)
async def solicitar_classificacao_ia(dados: RequisicaoAnaliseIA):
    try:
        # No Taskiq, usamos '.kiq()' de forma assíncrona para enviar os parâmetros à fila
        task = await executar_pipeline.kiq(
            id_gleba=dados.id_gleba,
            cultura_declarada=dados.cultura_declarada,
            id_produtor=dados.id_produtor
        )

        return {
            "mensagem": "Pipeline iniciado com sucesso",
            "task_id": task.task_id, # Atributo correto no Taskiq é task_id
            "status": "PROCESSANDO",
            "status_url": f"/api/v1/ia/status/{task.task_id}"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao enfileirar task: {str(e)}"
        )


# ----------------------------
# 2. STATUS TASKIQ (AJUSTADO)
# ----------------------------
@router.get("/status/{task_id}")
async def obter_status(task_id: str):
    try:
        # Buscamos o estado diretamente no backend de resultados do Redis configurado no broker
        result_backend = broker.result_backend

        if not result_backend:
            raise HTTPException(status_code=500, detail="Backend de resultados não configurado.")

        # CORREÇÃO: Altera de .is_ready para .is_result_ready do Taskiq
        is_ready = await result_backend.is_result_ready(task_id)

        if not is_ready:
            return {"task_id": task_id, "status": "PROCESSANDO"} # Alterado para 'PROCESSANDO' para fazer mais sentido

        # Coleta o objeto de resultado do Redis
        task_result = await result_backend.get_result(task_id)

        # Verifica se o código da tarefa disparou alguma exceção interna não tratada
        if task_result.is_err:
            return {"task_id": task_id, "status": "FALHA", "erro": str(task_result.error)}

        # Retorna o dicionário de sucesso gerado pelo VMGPipeline.executar()
        return {
            "task_id": task_id,
            "status": "SUCESSO",
            "resultado": task_result.return_value
        }

    except Exception as e:
        return {"task_id": task_id, "status": "FALHA", "erro": str(e)}

# ----------------------------
# 3. CLASSIFICAÇÕES RECENTES (CORRIGIDO UTC E NAIVE)
# ----------------------------
@router.get("/classificacoes/atuais", response_model=List[schema.ClassificacaoResponse])
async def listar_classificacoes_atuais(db: AsyncSession = Depends(get_db)):
    # datetime.now(timezone.utc) previne DeprecationWarning, .replace(tzinfo=None) remove o fuso para o Postgres
    limite = (datetime.now(timezone.utc) - timedelta(days=90)).replace(tzinfo=None)

    stmt = select(ClassificacaoCultura).where(
        ClassificacaoCultura.data_classificacao >= limite
    )

    result = await db.execute(stmt)
    return result.scalars().all()


# ----------------------------
# 4. HISTÓRICO (CORRIGIDO UTC E NAIVE)
# ----------------------------
@router.get("/historico", response_model=List[schema.ClassificacaoResponse])
async def historico(meses: int = 60, db: AsyncSession = Depends(get_db)):
    if meses > 60:
        raise HTTPException(400, "Máximo 60 meses")

    # Remove o fuso horário para bater com o tipo TIMESTAMP WITHOUT TIME ZONE
    limite = (datetime.now(timezone.utc) - timedelta(days=meses * 30)).replace(tzinfo=None)

    stmt = (
        select(ClassificacaoCultura)
        .where(ClassificacaoCultura.data_classificacao >= limite)
        .order_by(ClassificacaoCultura.data_classificacao.desc())
    )

    result = await db.execute(stmt)
    return result.scalars().all()


# ----------------------------
# 5. MÉTRICAS IA
# ----------------------------
@router.get("/metricas-assertividade", response_model=schema.MetricasAssertividadeResponse)
async def metricas(safra: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(ClassificacaoCultura).where(
        ClassificacaoCultura.cultura_real.isnot(None)
    )

    if safra:
        stmt = stmt.where(ClassificacaoCultura.safra == safra)

    result = await db.execute(stmt)
    dados = result.scalars().all()

    total = len(dados)

    if total == 0:
        return {
            "total_amostras": 0,
            "verdadeiros_positivos": 0,
            "falsos_positivos": 0,
            "falsos_negativos": 0,
            "exatidao_global": 0.0,
            "precisao": 0.0,
            "revocacao_sensibilidade": 0.0,
            "f1_score": 0.0
        }

    vp = sum(1 for d in dados if d.cultura_predita == d.cultura_real)
    fp = total - vp
    fn = total - vp

    precisao = vp / (vp + fp) if (vp + fp) else 0
    recall = vp / (vp + fn) if (vp + fn) else 0
    f1 = (2 * precisao * recall / (precisao + recall)) if (precisao + recall) else 0

    return {
        "total_amostras": total,
        "verdadeiros_positivos": vp,
        "falsos_positivos": fp,
        "falsos_negativos": fn,
        "exatidao_global": round(vp / total, 4),
        "precisao": round(precisao, 4),
        "revocacao_sensibilidade": round(recall, 4),
        "f1_score": round(f1, 4)
    }


# ----------------------------
# 6. DOCUMENTOS
# ----------------------------
@router.get("/documentos", response_model=List[schema.DocumentoResponse])
async def listar_docs(db: AsyncSession = Depends(get_db)):
    stmt = select(DocumentoTecnico).order_by(DocumentoTecnico.data_upload.desc())

    result = await db.execute(stmt)
    return result.scalars().all()


# ----------------------------
# 7. UPLOAD (CORRIGIDO UTC)
# ----------------------------
@router.post("/documentos/upload", response_model=schema.DocumentoResponse)
async def upload(
        titulo: str = Form(...),
        tipo: str = Form(...),
        arquivo: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    if tipo not in ["atestado_capacidade", "aprovacao_metodologia"]:
        raise HTTPException(400, "Tipo inválido")

    # timestamp com fuso horário limpo
    timestamp_atual = datetime.now(timezone.utc).timestamp()
    path = os.path.join(UPLOAD_DIR, f"{timestamp_atual}_{arquivo.filename}")

    with open(path, "wb") as f:
        shutil.copyfileobj(arquivo.file, f)

    doc = DocumentoTecnico(
        titulo=titulo,
        tipo=tipo,
        caminho_arquivo=path
    )

    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return doc


# ----------------------------
# 8. SALVAR RESULTADO (INTERNO)
# ----------------------------
@router.post("/salvar-resultado-internal", include_in_schema=False)
async def salvar_internal(payload: PayloadSalvarIA, db: AsyncSession = Depends(get_db)):
    obj = ClassificacaoCultura(
        gleba_id=payload.gleba_id,
        safra=payload.safra,
        cultura_predita=payload.cultura_predita,
        cultura_real=payload.cultura_real,
        confianca_ia=payload.confianca_ia
    )

    db.add(obj)
    await db.commit()

    return {"status": "ok"}
