import sys
import asyncio

# Garante o seletor clássico de sockets do Windows logo na inicialização do módulo
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.models.classificacao_model import ClassificacoesCulturas, CertificadosBpa
from app.models.gleba_model import GlebaModel, MunicipioIbge, DocumentoTecnico
from app.models.models_ledger import AtestadosVmgLedger
from app.models.notificacao_model import NotificacaoUsuarioModel
from app.services.celery.broker import broker
from app.database.factory.celery_session import get_session
from app.services.ia_pipeline import VMGPipeline

def build_pipeline(session):
    from app.repository.compliance_repository import ComplianceRepository
    from app.repository.zarc_repository import ZarcRepository
    from app.repository.repositories import (
        SoloRepository, ClimaRepository, BpaRepository, LedgerPersistenceRepository
    )


    return VMGPipeline(
        compliance_repo=ComplianceRepository(session),
        zarc_repo=ZarcRepository(session),
        solo_repo=SoloRepository(session),
        clima_repo=ClimaRepository(session),
        bpa_repo=BpaRepository(session),
        ledger_repo=LedgerPersistenceRepository(session),
        db_session=session
    )

@broker.task(task_name="executar_pipeline")
async def executar_pipeline(id_gleba: int, cultura_declarada: str, id_produtor: int = None):
    # Força uma pausa rápida de 10ms para permitir que o loop limpe
    # buffers de rede pendentes do Windows antes de criar os drivers de I/O
    await asyncio.sleep(0.01)

    SessionMaker, engine = get_session()

    try:
        async with SessionMaker() as session:
            pipeline = build_pipeline(session)

            resultado = await pipeline.executar(
                id_gleba=id_gleba,
                cultura_declarada=cultura_declarada,
                id_produtor=id_produtor
            )

            await session.commit()
            return resultado

    finally:
        # Destrói fisicamente o socket TCP do Postgres evitando sockets zumbis
        await engine.dispose()
