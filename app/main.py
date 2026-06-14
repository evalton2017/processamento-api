import time
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.routers import produtor, monitoramento, produtividade_router, ia_router, auditoria_router

from app.config.logger_config import setup_logs

# 1. Ativa a configuração global de logs do sistema ANTES de iniciar o app
setup_logs()
logger = logging.getLogger("api-sistema")

app = FastAPI(
    title="Infraestrutura VMG - Agro Brasil + Sustentável",
    description="API de Monitoramento Complementar e Verificação Agrícola",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    version="1.0.0"
)

# 2. Middleware para interceptar e logar todas as requisições HTTP do sistema
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Processa a requisição nas rotas
    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000

    # Registra no log do sistema o resultado da operação
    logger.info(
        f"Método: {request.method} | "
        f"Rota: {request.url.path} | "
        f"Status: {response.status_code} | "
        f"Tempo: {process_time:.2f}ms"
    )

    return response

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Inclusão dos módulos de rotas
app.include_router(produtor.router)
app.include_router(monitoramento.router)
app.include_router(produtividade_router.router)
app.include_router(ia_router.router)
app.include_router(auditoria_router.router)

@app.get("/health", tags=["Infraestrutura"])
async def health_check():
    logger.info("Verificação de saúde (health check) executada.")
    return {"status": "OPERANTE", "disponibilidade_sla": "99.9%"}

# Bloco de inicialização do sistema
if __name__ == "__main__":
    import uvicorn
    # Mantido o objeto 'app' direto para compatibilidade e estabilidade no Windows
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
