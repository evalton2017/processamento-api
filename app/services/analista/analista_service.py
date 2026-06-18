import math
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class AnalistaService:
    def __init__(self, db):
        self.db = db
        from app.repository.analista_repository import AnalistaRepository
        self.repository = AnalistaRepository(db)

    async def buscar_listagem_novo_modelo(self, filtros: Dict[str, Any], page: int, limit: int) -> Dict[str, Any]:
        """
        Orquestra a contagem e a listagem de glebas aplicando as regras de auditoria do Ledger.
        """
        logger.info(f"Processando listagem via Ledger no Service para a página {page} com limite {limit}.")

        # 1. Busca a contagem total utilizando a nova infraestrutura de Joins do Ledger
        total_registros = await self.repository.contar_total_glebas(filtros)

        # 2. CORREÇÃO: Alinhado para chamar o nome do método atualizado no repositório
        dados_linhas = await self.repository.listar_glebas_modelo_ledger(filtros, page, limit)

        # 3. Calcula o número total de páginas (Ex: 2456 registros de 8 em 8 = 307 páginas)
        total_paginas = math.ceil(total_registros / limit) if total_registros > 0 else 1

        return {
            "total_registros": total_registros,
            "pagina_atual": page,
            "total_paginas": total_paginas,
            "dados": dados_linhas
        }
