import json
import logging
import os
from typing import List, Dict, Any
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://:duke2214@127.0.0.1:6379/0")

class ZarcCacheService:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.CHAVE_CULTURAS = "vmg:zarc:culturas_disponiveis"

    async def salvar_culturas_inicializacao(self, culturas: List[Dict[str, Any]]) -> None:
        """
        Persiste a lista de culturas do ZARC no Redis de forma imutável para o ciclo de vida.
        """
        try:
            payload = json.dumps(culturas, default=str) # default=str trata o campo data_cadastro/datetime
            await self.redis.set(self.CHAVE_CULTURAS, payload)
            logger.info(f"💾 Redis: {len(culturas)} culturas do ZARC carregadas em cache com sucesso!")
        except Exception as e:
            logger.error(f"❌ Falha ao salvar culturas no cache Redis: {str(e)}")

    async def obter_culturas_cache(self) -> List[Dict[str, Any]]:
        """
        Recupera as culturas salvas na memória RAM de forma ultra-rápida O(1).
        """
        try:
            dados = await self.redis.get(self.CHAVE_CULTURAS)
            if dados:
                return json.loads(dados)
        except Exception as e:
            logger.error(f"❌ Erro ao ler culturas do cache Redis: {str(e)}")
        return []
