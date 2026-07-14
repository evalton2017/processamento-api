# app/database/session.py
import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/vmg_database"
)

# Garante o dialeto assíncrono correto para o driver asyncpg
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Engine Assíncrono único e robusto para o FastAPI e Roteadores
async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Evita conexões caídas na VPS
    pool_size=20,
    max_overflow=10
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

# Dependência Única utilizada em todos os Roteadores da API
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Injeta sessões assíncronas isoladas por ciclo de vida da requisição."""
    async with AsyncSessionLocal() as session:
        yield session
