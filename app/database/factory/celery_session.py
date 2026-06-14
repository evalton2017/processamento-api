import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env para o sistema
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL_CELERY")

if not DATABASE_URL or "IP_DA_SUA_VPS" in DATABASE_URL:
    raise ValueError("ERRO: O arquivo .env não foi carregado ou a URL está incorreta!")

def get_session():
    """Gera sessões assíncronas utilizando o driver psycopg, tolerante a redes remotas."""
    engine = create_async_engine(
        DATABASE_URL,
        poolclass=NullPool,
        connect_args={
            "sslmode": "disable",
            "connect_timeout": 15
        }
    )

    SessionMaker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    return SessionMaker, engine
