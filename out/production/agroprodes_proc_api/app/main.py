import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
from requests import session

from app.cache.cache_service import ZarcCacheService
from app.database.factory.celery_session import get_session
from app.repository.dominio_repository import DomínioRepository
from app.repository.zarc_repository import ZarcRepository
# Imports originais do ecossistema de rotas e modelos do Agroprodes
from app.routers import (produtor_router, monitoramento, produtividade_router, ia_router, treinamento_router,
                         auditoria_router, dashboard_analista_router, analista_router, dashboard_produtor_router, gleba_router)
import app.models


# Configuração do Logger unificado do sistema
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")

# 1. 🟢 Instanciação global e assíncrona do Cliente Redis
# Alinhe as credenciais com a sua VPS ou ambiente Docker local (Ex: porta 6379)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

# 2. 🟢 Definição do Gerenciador de Ciclo de Vida (Lifespan)
@asynccontextmanager
async def lifespan_manager(app: FastAPI):

    logger.info("⚡ Inicializando Infraestrutura VMG e aquecendo Cache do Redis...")
    SessionMaker, engine = get_session()
    async with SessionMaker() as session:
        dominioRepo = DomínioRepository(session)
        cache_service = ZarcCacheService(redis_client)

        try:
            # Executa a sua consulta SQL customizada (WITH culturas_agrupadas...)
            linhas_sql = await dominioRepo.listar_culturas(ativo=True, grupo="GRÃOS")

            # Converte os objetos Row/Tuple do SQLAlchemy em dicionários serializáveis
            culturas_formatadas = [
                {
                    "id": int(row.id),
                    "codigo": str(row.codigo),
                    "nome": str(row.nome),
                    "grupo": str(row.grupo),
                    "ativo": bool(row.ativo),
                    "permite_zarc": bool(row.permite_zarc),
                    "data_cadastro": str(row.data_cadastro)
                }
                for row in linhas_sql
            ]

            # Persiste os dados na memória estável do Redis para acesso instantâneo O(1)
            await cache_service.salvar_culturas_inicializacao(culturas_formatadas)

        except Exception as cache_err:
            # Trava o startup em log crítico se a query ou a conexão com o Redis quebrar
            logger.critical(f"❌ Erro crítico no aquecimento de cache ZARC: {str(cache_err)}")

    yield

    logger.info("🔌 Desligando conexões ativas do Redis no encerramento do container...")
    await redis_client.close()

app = FastAPI(
    title="Infraestrutura VMG - Agro Brasil + Sustentável",
    description="API de Monitoramento Complementar e Verificação Agrícola",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    version="1.0.0",
    lifespan=lifespan_manager  # Injetado aqui
)

# Configuração de CORS intacta
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Inclusão dos módulos de rotas originais
app.include_router(dashboard_analista_router.router)
app.include_router(dashboard_produtor_router.router)
app.include_router(analista_router.router)
app.include_router(produtor_router.router)
app.include_router(gleba_router.router)
app.include_router(monitoramento.router)
app.include_router(produtividade_router.router)
app.include_router(ia_router.router)
app.include_router(auditoria_router.router)
app.include_router(treinamento_router.router)


@app.get("/health", tags=["Infraestrutura"])
async def health_check():
    return {"status": "OPERANTE", "disponibilidade_sla": "99.9%"}

# Bloco de inicialização do sistema para estabilidade no Windows
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
