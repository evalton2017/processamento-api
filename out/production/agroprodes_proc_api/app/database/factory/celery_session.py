import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
from sqlalchemy.orm import configure_mappers
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL or "IP_DA_SUA_VPS" in DATABASE_URL:
    raise ValueError("ERRO: O arquivo .env não foi carregado ou a URL está incorreta!")

def get_session():

    configure_mappers()

    engine = create_async_engine(
        DATABASE_URL,
        poolclass=NullPool,
        connect_args={
            "timeout": 15,
            "ssl": False
        }
    )

    SessionMaker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    return SessionMaker, engine
