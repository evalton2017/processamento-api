from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from typing import Dict, Any

class DashboardProdutorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def obter_nome_produtor(self, id_produtor: int) -> str:
        query = select(text("nome")).select_from(text("agroprods.pessoa")).where(text("id = :id"))
        result = await self.session.execute(query, {"id": id_produtor})
        return result.scalar() or "Produtor Rural"

    async def consultar_metricas_consolidadas(self, id_produtor: int, safra: str) -> Dict[str, Any]:
        """
        Executa agregação de dados no schema audit garantindo isolamento anti-cartesiano.
        """
        sql = text("""
                   WITH ultimos_atestados AS (
                       SELECT
                           id_gleba,
                           status_validacao,
                           hash_relatorio,
                           ROW_NUMBER() OVER(PARTITION BY id_gleba ORDER BY data_emissao DESC, id_atestado DESC) as rn
                       FROM audit.atestados_vmg_ledger
                   ),
                        dados_auditados_produtor AS (
                            SELECT
                                g.id_gleba,
                                g.area_hectares,
                                g.codigo_municipio,
                                am.status_validacao,
                                hl.conflito_socioambiental,
                                cl.safra
                            FROM agroprods.glebas g
                                     JOIN ultimos_atestados am ON g.id_gleba = am.id_gleba AND am.rn = 1
                                     JOIN audit.ia_classificacao_cultura_ledger cl ON g.id_gleba = cl.id_gleba AND am.hash_relatorio = cl.hash_bloco
                                     JOIN audit.historico_laudos_ambientais_ledger hl ON g.id_gleba = hl.id_gleba AND am.hash_relatorio = hl.hash_bloco
                            WHERE g.id_produtor = :id_produtor AND cl.safra = :safra
                        )
                   SELECT
                       COUNT(id_gleba) as total_glebas,
                       COALESCE(SUM(area_hectares), 0) as area_total,
                       COUNT(DISTINCT codigo_municipio) as total_municipios,
                       COUNT(CASE WHEN status_validacao = 'APROVADO' THEN 1 END) as total_atestados,
                       COUNT(CASE WHEN conflito_socioambiental = TRUE THEN 1 END) as total_alertas,
                       COALESCE(SUM(CASE WHEN conflito_socioambiental = FALSE THEN area_hectares ELSE 0 END), 0) as area_conforme
                   FROM dados_auditados_produtor;
                   """)

        result = await self.session.execute(sql, {"id_produtor": id_produtor, "safra": safra})
        return result.mappings().fetchone()
