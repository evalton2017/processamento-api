import os
import sys
import asyncio
from pathlib import Path

# ==============================================================================
# CONFIGURAÇÃO DO AMBIENTE GDAL / PROJ
# Deve ocorrer ANTES de qualquer import que utilize rasterio ou pyproj
# ==============================================================================

# Remove configurações herdadas do ambiente
os.environ.pop("PROJ_LIB", None)
os.environ.pop("GDAL_DATA", None)

# Desabilita downloads automáticos do PROJ
os.environ["PROJ_NETWORK"] = "OFF"

# Utiliza a definição oficial EPSG
os.environ["GTIFF_SRS_SOURCE"] = "EPSG"

# Procura automaticamente o proj_data da instalação atual do Python
python_base = Path(sys.executable).parent

possiveis_caminhos = [
    python_base / "Lib" / "site-packages" / "rasterio" / "proj_data",
    python_base.parent / "Lib" / "site-packages" / "rasterio" / "proj_data",
    ]

for caminho in possiveis_caminhos:

    if caminho.exists():

        os.environ["PROJ_LIB"] = str(caminho)

        break

# ==============================================================================
# WINDOWS EVENT LOOP
# ==============================================================================

if sys.platform == "win32":

    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

# ==============================================================================
# IMPORTS DA APLICAÇÃO
# ==============================================================================

from app.services.celery.broker import broker
from app.database.factory.celery_session import get_session
from app.services.pipelineia.ia_pipeline import VMGPipeline


def build_pipeline(session):

    from app.repository.compliance_repository import ComplianceRepository
    from app.repository.zarc_repository import ZarcRepository

    from app.repository.repositories import (
        SoloRepository,
        ClimaRepository,
        BpaRepository,
        LedgerPersistenceRepository,
    )

    return VMGPipeline(
        compliance_repo=ComplianceRepository(session),
        zarc_repo=ZarcRepository(session),
        solo_repo=SoloRepository(session),
        clima_repo=ClimaRepository(session),
        bpa_repo=BpaRepository(session),
        ledger_repo=LedgerPersistenceRepository(session),
        db_session=session,
    )


@broker.task(task_name="executar_pipeline")
async def executar_pipeline(
        id_gleba: int,
        cultura_declarada: str,
        id_produtor: int = None,
):

    # Permite limpeza do loop de eventos no Windows
    await asyncio.sleep(0.01)
    SessionMaker, engine = get_session()
    try:
        async with SessionMaker() as session:
            pipeline = build_pipeline(session)
            resultado = await pipeline.executar(
                id_gleba=id_gleba,
                cultura_declarada=cultura_declarada,
                id_produtor=id_produtor,
            )
            await session.commit()
            return resultado
    finally:
        await engine.dispose()