from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import produtor, monitoramento, produtividade_router, ia_router, auditoria_router

app = FastAPI(
    title="Infraestrutura VMG - Agro Brasil + Sustentável",
    description="API de Monitoramento Complementar e Verificação Agrícola",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    version="1.0.0"
)

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
    return {"status": "OPERANTE", "disponibilidade_sla": "99.9%"}

# Bloco de inicialização do sistema
if __name__ == "__main__":
    import uvicorn
    # Mantido o objeto 'app' direto para compatibilidade e estabilidade no Windows
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
