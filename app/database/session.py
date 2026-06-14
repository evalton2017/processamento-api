import os
import urllib.parse

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine

# =========================
# DATABASE URLS
# =========================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/vmg_db"
)

LEDGER_DATABASE_URL = os.getenv(
    "LEDGER_DATABASE_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/ledger_db"
)

# =========================
# ASYNC ENGINES (FastAPI / IA PIPELINE)
# =========================

engine_principal = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    future=True,
)

engine_ledger = create_async_engine(
    LEDGER_DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    future=True,
)

# =========================
# SESSION MAKERS
# =========================

AsyncSessionPrincipal = async_sessionmaker(
    bind=engine_principal,
    class_=AsyncSession,
    expire_on_commit=False,
)

AsyncSessionLedger = async_sessionmaker(
    bind=engine_ledger,
    class_=AsyncSession,
    expire_on_commit=False,
)

# =========================
# BASE ORM
# =========================

Base = declarative_base()

# =========================
# DEPENDENCY FASTAPI
# =========================

async def get_db():
    async with AsyncSessionPrincipal() as session:
        yield session

async def get_ledger_db():
    async with AsyncSessionLedger() as session:
        yield session

# =========================
# SYNC ENGINE (somente se precisar Alembic / scripts)
# =========================

SYNC_DATABASE_URL = DATABASE_URL.replace(
    "postgresql+asyncpg://",
    "postgresql+psycopg2://"
)

if "%" in SYNC_DATABASE_URL:
    SYNC_DATABASE_URL = urllib.parse.unquote(SYNC_DATABASE_URL)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,          # Mantém conexões prontas para a API HTTP
    max_overflow=20,
    pool_pre_ping=True,    # Testa se a conexão caiu antes de usá-la (Evita o ConnectionDoesNotExistError)
    pool_recycle=1800      # Recicla conexões a cada 30 minutos
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Generator utilizado pelo Depends(get_db) nas rotas do FastAPI
async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()