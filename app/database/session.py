import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

schema_name = 'agroprods'
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/vmg_db")
LEDGER_DATABASE_URL = os.getenv("LEDGER_DATABASE_URL", "postgresql+asyncpg://user:pass@vps66374.publiccloud.com.br:5434/ledger_db")

engine_principal = create_async_engine(DATABASE_URL, echo=False, pool_size=15, max_overflow=5)
engine_ledger = create_async_engine(LEDGER_DATABASE_URL, echo=False, pool_size=10, max_overflow=5)

# 3. Gerenciadores de Sessão locais
AsyncSessionPrincipal = sessionmaker(bind=engine_principal, class_=AsyncSession, expire_on_commit=False)
AsyncSessionLedger = sessionmaker(bind=engine_ledger, class_=AsyncSession, expire_on_commit=False)


Base = declarative_base()

# 4. Dependência injetável para o Banco Geográfico Principal (Rotas de Clima, IA, Produtor)
async def get_db():
    async with AsyncSessionPrincipal() as session:
        try:
            yield session
        finally:
            await session.close()

# 5. Dependência injetável para a Base do Ledger Imutável na VPS (Rotas de Auditoria e LGPD)
async def get_ledger_db():
    async with AsyncSessionLedger() as session:
        try:
            yield session
        finally:
            await session.close()

SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

engine_sync = create_engine(SYNC_DATABASE_URL, pool_size=5, max_overflow=10)
SessionLocalSync = sessionmaker(autocommit=False, autoflush=False, bind=engine_sync)