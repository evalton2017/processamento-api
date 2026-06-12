import os
import shutil
from datetime import datetime, timedelta
from typing import List, Optional

from celery.result import AsyncResult
from fastapi import APIRouter, status, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import app.database.schemas as schema
from app.database.database import ClassificacaoCultura, DocumentoTecnico
from app.database.session import get_db
from app.services.ia_pipeline import executar_classificacao_ia_vmg, celery_app

router = APIRouter(prefix="/api/v1/ia", tags=["Módulo de Inteligência Artificial"])
UPLOAD_DIR = "./armazenamento_documentos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class RequisicaoAnaliseIA(BaseModel):
    id_gleba: int
    cultura_declarada: str

@router.post("/classificar", status_code=status.HTTP_202_ACCEPTED)
async def solicitar_classificacao_ia(dados: RequisicaoAnaliseIA):
    try:
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
    res = AsyncResult(task_id, app=celery_app)
    if res.state == 'PENDING':
        return {"task_id": task_id, "status": "AGUARDANDO_WORKER"}
    elif res.state == 'SUCCESS':
        return {"task_id": task_id, "status": "SUCESSO", "resultado": res.result}
    elif res.state == 'FAILURE':
        return {"task_id": task_id, "status": "FALHA", "erro": str(res.info)}
    return {"task_id": task_id, "status": res.state}

# --- 1. CROP CLASSIFICATION COMPONENT ---
@router.get("/classificacoes/atuais", response_model=List[schema.ClassificacaoResponse])
async def listar_classificacoes_atuais(db_session: AsyncSession = Depends(get_db)):
    # Padrão assíncrono: cria o select e executa com await
    stmt = select(ClassificacaoCultura).where(
        ClassificacaoCultura.data_classificacao >= datetime.utcnow() - timedelta(days=90)
    )
    result = await db_session.execute(stmt)
    return result.scalars().all()

# --- 2. TIMELINE SLIDER COMPONENT (60 meses) ---
@router.get("/historico", response_model=List[schema.ClassificacaoResponse])
async def obtener_historico_timeline(meses_retroceder: int = 60, db_session: AsyncSession = Depends(get_db)):
    if meses_retroceder > 60:
        raise HTTPException(status_code=400, detail="O limite máximo permitido é de 60 meses.")

    data_limite = datetime.utcnow() - timedelta(days=meses_retroceder * 30)

    # 1. Monta a query expressa em select (padrão v2.0)
    stmt = select(ClassificacaoCultura).where(
        ClassificacaoCultura.data_classificacao >= data_limite
    ).order_by(ClassificacaoCultura.data_classificacao.desc())

    # 2. OBRIGATÓRIO: Executa com await para evitar o erro MissingGreenlet
    result = await db_session.execute(stmt)

    # 3. Extrai os resultados escalares de dentro do objeto executado
    return result.scalars().all()


# --- 3. ASSERTIVENESS VALIDATION COMPONENT (Anexo VI) ---
@router.get("/metricas-assertividade", response_model=schema.MetricasAssertividadeResponse)
async def calcular_metricas_anexo_vi(safra: Optional[str] = None, db_session: AsyncSession = Depends(get_db)):
    # 1. Monta a query inicial filtrando registros válidos
    stmt = select(ClassificacaoCultura).where(ClassificacaoCultura.cultura_real.isnot(None))
    if safra:
        stmt = stmt.where(ClassificacaoCultura.safra == safra)

    # 2. OBRIGATÓRIO: Executa de forma assíncrona com await
    result = await db_session.execute(stmt)
    dados = result.scalars().all()
    total = len(dados)

    if total == 0:
        return {
            "total_amostras": 0, "verdadeiros_positivos": 0, "falsos_positivos": 0, "falsos_negativos": 0,
            "exatidao_global": 0.0, "precisao": 0.0, "revocacao_sensibilidade": 0.0, "f1_score": 0.0
        }

    vp = fp = fn = 0
    for item in dados:
        if item.cultura_predita == item.cultura_real:
            vp += 1
        else:
            fp += 1
            fn += 1

    exatidao = vp / total
    precisao = vp / (vp + fp) if (vp + fp) > 0 else 0.0
    revocacao = vp / (vp + fn) if (vp + fn) > 0 else 0.0
    f1 = 2 * (precisao * revocacao) / (precisao + revocacao) if (precisao + revocacao) > 0 else 0.0

    return {
        "total_amostras": total,
        "verdadeiros_positivos": vp,
        "falsos_positivos": fp,
        "falsos_negativos": fn,
        "exatidao_global": round(exatidao, 4),
        "precisao": round(precisao, 4),
        "revocacao_sensibilidade": round(revocacao, 4),
        "f1_score": round(f1, 4)
    }

# --- 4. TECHNICAL APTITUDE UPLOAD COMPONENT (LISTAGEM CORRIGIDA) ---
@router.get("/documentos", response_model=List[schema.DocumentoResponse])
async def listar_documentos_tecnicos(db_session: AsyncSession = Depends(get_db)):
    """
    Lista todos os documentos técnicos salvos usando o padrão assíncrono correto v2.0.
    """
    # 1. Cria a instrução select (Substitui o antigo .query)
    stmt = select(DocumentoTecnico).order_by(DocumentoTecnico.data_upload.desc())

    # 2. OBRIGATÓRIO: Executa de forma assíncrona com await para evitar o erro MissingGreenlet
    result = await db_session.execute(stmt)

    # 3. Extrai os escalares da consulta
    return result.scalars().all()


# --- 4. TECHNICAL APTITUDE UPLOAD COMPONENT (UPLOAD CORRIGIDO) ---
@router.post("/documentos/upload", response_model=schema.DocumentoResponse)
async def upload_documento_tecnico(
        titulo: str = Form(...),
        tipo: str = Form(..., description="'atestado_capacidade' ou 'aprovacao_metodologia'"),
        arquivo: UploadFile = File(...),
        db_session: AsyncSession = Depends(get_db)
):
    """
    Recebe os arquivos binários de relatórios e atestados e persiste no Postgres de forma assíncrona.
    """
    if tipo not in ["atestado_capacidade", "aprovacao_metodologia"]:
        raise HTTPException(status_code=400, detail="Tipo de documento inválido.")

    # Salva o arquivo fisicamente no disco local
    caminho_final = os.path.join(UPLOAD_DIR, f"{datetime.utcnow().timestamp()}_{arquivo.filename}")
    with open(caminho_final, "wb") as buffer:
        shutil.copyfileobj(arquivo.file, buffer)

    novo_doc = DocumentoTecnico(
        titulo=titulo,
        tipo=tipo,
        caminho_arquivo=caminho_final
    )

    # Operações assíncronas corretas com a sessão do banco de dados
    db_session.add(novo_doc)
    await db_session.commit()
    await db_session.refresh(novo_doc)

    return novo_doc
