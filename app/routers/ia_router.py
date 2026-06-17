import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, status, HTTPException, Depends
from fastapi import UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import app.dto.schemas as schema
from app.database.session import get_async_db
from app.models.gleba_model import DocumentoTecnico
# Importação da tabela imutável de classificação do Ledger para as rotas de métricas e histórico
from app.models.models_ledger import IaClassificacaoCulturaLedger
# IMPORTAÇÃO DO TASKIQ
from app.services.celery.celery_task import executar_pipeline, broker

router = APIRouter(prefix="/api/v1/ia", tags=["IA Pipeline"])

UPLOAD_DIR = "./armazenamento_documentos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ----------------------------
# MODELS DTO
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
# 1. DISPARAR PIPELINE (TASKIQ ASSÍNCRONO)
# ----------------------------
@router.post("/classificar", status_code=status.HTTP_202_ACCEPTED)
async def solicitar_classificacao_ia(dados: RequisicaoAnaliseIA):
    try:
        # Enfileiramento em background utilizando o broker do Taskiq
        task = await executar_pipeline.kiq(
            id_gleba=dados.id_gleba,
            cultura_declarada=dados.cultura_declarada,
            id_produtor=dados.id_produtor
        )

        return {
            "mensagem": "Pipeline iniciado com sucesso",
            "task_id": task.task_id,
            "status": "PROCESSANDO",
            "status_url": f"/api/v1/ia/status/{task.task_id}"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao enfileirar task no gerenciador de processos: {str(e)}"
        )


# ----------------------------
# 2. STATUS TASKIQ
# ----------------------------
@router.get("/status/{task_id}")
async def obter_status(task_id: str):
    try:
        result_backend = broker.result_backend

        if not result_backend:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Backend de resultados do Redis não configurado."
            )

        is_ready = await result_backend.is_result_ready(task_id)

        if not is_ready:
            return {"task_id": task_id, "status": "PROCESSANDO"}

        task_result = await result_backend.get_result(task_id)

        if task_result.is_err:
            return {"task_id": task_id, "status": "FALHA", "erro": str(task_result.error)}

        return {
            "task_id": task_id,
            "status": "SUCESSO",
            "resultado": task_result.return_value
        }

    except Exception as e:
        return {"task_id": task_id, "status": "FALHA", "erro": str(e)}


# ----------------------------
# 3. CLASSIFICAÇÕES RECENTES (AJUSTADO PARA SCHEMA AUDIT)
# ----------------------------
@router.get("/classificacoes/atuais", response_model=List[schema.ClassificacaoResponse])
async def listar_classificacoes_atuais(db: AsyncSession = Depends(get_async_db)):
    # Remove fuso horário para bater com o tipo TIMESTAMP do PostgreSQL
    limite = (datetime.now(timezone.utc) - timedelta(days=90)).replace(tzinfo=None)

    # Busca as informações diretamente no banco imutável do Ledger
    stmt = select(IaClassificacaoCulturaLedger).where(
        IaClassificacaoCulturaLedger.data_analise >= limite
    )

    result = await db.execute(stmt)
    return result.scalars().all()


# ----------------------------
# 4. HISTÓRICO DE 60 MESES DA PORTARIA (AJUSTADO PARA SCHEMA AUDIT)
# ----------------------------
@router.get("/historico", response_model=List[schema.ClassificacaoResponse])
async def historico(meses: int = 60, db: AsyncSession = Depends(get_async_db)):
    if meses > 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inconformidade com a Portaria: Auditorias limitadas aos últimos 60 meses."
        )

    limite = (datetime.now(timezone.utc) - timedelta(days=meses * 30)).replace(tzinfo=None)

    stmt = (
        select(IaClassificacaoCulturaLedger)
        .where(IaClassificacaoCulturaLedger.data_analise >= limite)
        .order_by(IaClassificacaoCulturaLedger.data_analise.desc())
    )

    result = await db.execute(stmt)
    return result.scalars().all()


# ----------------------------
# 5. CÁLCULO DE MÈTRICAS DE ASSERTIVIDADE (ANEXO VI DA PORTARIA)
# ----------------------------
@router.get("/metricas-assertividade", response_model=schema.MetricasAssertividadeResponse)
async def metricas(safra: Optional[str] = None, db: AsyncSession = Depends(get_async_db)):
    """
    Consolida as métricas oficiais de desempenho da IA exigidas para fiscalização
    semestral da Secretaria, baseando-se nos registros estáveis do ledger.
    """
    stmt = select(IaClassificacaoCulturaLedger)

    if safra:
        stmt = stmt.where(IaClassificacaoCulturaLedger.safra == safra)

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

    vp = 0  # Verdadeiros Positivos (Cultura identificada condizente com a declarada)
    fp = 0  # Falsos Positivos (Divergências identificadas pela IA)
    fn = 0  # Falsos Negativos (Casos em que a condução foi classificada como divergente)

    for d in dados:
        if d.status_conducao == "CONDIZENTE":
            vp += 1
        else:
            fp += 1
            fn += 1

    exatidao = vp / total
    precisao = vp / (vp + fp) if (vp + fp) > 0 else 0.0
    recall = vp / (vp + fn) if (vp + fn) > 0 else 0.0
    f1 = (2 * precisao * recall) / (precisao + recall) if (precisao + recall) > 0 else 0.0

    return {
        "total_amostras": total,
        "verdadeiros_positivos": vp,
        "falsos_positivos": fp,
        "falsos_negativos": fn,
        "exatidao_global": round(exatidao, 4),
        "precisao": round(precisao, 4),
        "revocacao_sensibilidade": round(recall, 4),
        "f1_score": round(f1, 4)
    }


# ----------------------------
# 6. DOCUMENTOS TÉCNICOS
# ----------------------------
@router.get("/documentos", response_model=List[schema.DocumentoResponse])
async def listar_docs(db: AsyncSession = Depends(get_async_db)):
    stmt = select(DocumentoTecnico).order_by(DocumentoTecnico.data_upload.desc())

    result = await db.execute(stmt)
    return result.scalars().all()
# ----------------------------
# 7. UPLOAD DE DOCUMENTOS TÉCNICOS (Itens 3.2 e 3.5 da Portaria)
# ----------------------------
@router.post("/documentos/upload", response_model=schema.DocumentoResponse, status_code=status.HTTP_201_CREATED)
async def upload(
        titulo: str = Form(...),
        tipo: str = Form(...),
        arquivo: UploadFile = File(...),
        db: AsyncSession = Depends(get_async_db)  # 🟢 CORREÇÃO: Sessão assíncrona estável
):
    """
    Realiza o upload e o registro de atestados de capacidade técnica (Item 3.2)
    e aprovações de metodologia (Item 3.5) exigidos para o credenciamento ministerial.
    """
    if tipo not in ["atestado_capacidade", "aprovacao_metodologia"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de documento inválido. Permitidos: 'atestado_capacidade' ou 'aprovacao_metodologia'."
        )

    # Timestamp limpo com UTC para nomeação de arquivo segura contra colisões
    timestamp_atual = int(datetime.now(timezone.utc).timestamp())
    nome_arquivo_seguro = f"{timestamp_atual}_{arquivo.filename.replace(' ', '_')}"
    path = os.path.join(UPLOAD_DIR, nome_arquivo_seguro)

    try:
        # Escrita assíncrona de blocos de arquivo em disco para evitar travamento do Event Loop
        with open(path, "wb") as f:
            shutil.copyfileobj(arquivo.file, f)

    except Exception as err_disco:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha de gravação física do documento no servidor: {str(err_disco)}"
        )

    # Bloco transacional atômico para persistência do metadado
    async with db.begin():
        doc = DocumentoTecnico(
            titulo=titulo,
            tipo=tipo,
            caminho_arquivo=path,
            data_upload=datetime.utcnow()  # Força data naive compatível com TIMESTAMP do banco
        )
        db.add(doc)
        await db.flush()  # Sincroniza o estado para capturar o ID gerado antes do encerramento do bloco

    return doc


# ----------------------------
# 8. SALVAR RESULTADO (INTERNO DO TRABALHADOR DE FILA)
# ----------------------------
@router.post("/salvar-resultado-internal", include_in_schema=False)
async def salvar_internal(
        payload: PayloadSalvarIA,
        db: AsyncSession = Depends(get_async_db)  # 🟢 CORREÇÃO: Sessão assíncrona estável
):
    """
    Endpoint privado de uso exclusivo dos workers em background (Taskiq)
    para registrar os vereditos da IA diretamente nas tabelas estáveis do Ledger.
    """
    async with db.begin():
        obj = IaClassificacaoCulturaLedger(
            id_gleba=payload.gleba_id,
            safra=payload.safra,
            cultura_identificada=payload.cultura_predita,
            cultura_declarada=payload.cultura_real or "N/A",
            status_conducao="CONDIZENTE" if payload.cultura_predita.upper() == (payload.cultura_real or "").upper() else "DIVERGENTE",
            percentual_confianca=payload.confianca_ia,
            hash_bloco=f"internal_task_sync_{payload.gleba_id}_{int(datetime.utcnow().timestamp())}"
        )
        db.add(obj)

    return {"status": "SUCESSO", "mensagem": "Resultado de inferência registrado no ledger de auditoria."}


