import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import urllib.parse

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



# 1. Trata a URL síncrona forçando o driver psycopg2 clássico
SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

# 2. Correção de segurança para decodificar caracteres especiais como %40 na senha
if "%" in SYNC_DATABASE_URL:
    # Desfaz a codificação de URL para que o psycopg2 entenda o '@' ou outros caracteres especiais na senha
    SYNC_DATABASE_URL = urllib.parse.unquote(SYNC_DATABASE_URL)

# 3. Criação da engine blindada contra erros de codec de texto latim
engine_sync = create_engine(
    SYNC_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    # Esta linha força o Postgres a devolver qualquer erro ou mensagem em UTF-8 puro, eliminando o erro de codec!
    connect_args={"client_encoding": "utf8"}
)

SessionLocalSync = sessionmaker(autocommit=False, autoflush=False, bind=engine_sync)
