from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from typing import List, Dict, Any,Optional

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

    async def obter_ultimo_laudo_detalhado(self, id_produtor: int, safra: str) -> Optional[Dict[str, Any]]:
        """
        Busca o último laudo de conformidade do Ledger para as glebas do produtor.
        Extrai o JSON detalhado e os booleanos estruturados pelo pipeline de IA.
        """
        sql = text("""
                   WITH ultimos_atestados AS (
                       SELECT id_gleba, hash_relatorio,
                              ROW_NUMBER() OVER(PARTITION BY id_gleba ORDER BY data_emissao DESC, id_atestado DESC) as rn
                       FROM audit.atestados_vmg_ledger
                   )
                   SELECT
                       g.area_hectares,
                       hl.conflito_socioambiental,
                       hl.conflito_prodes,
                       hl.conflito_ibama_icmbio,
                       hl.conflito_comunidades,
                       hl.laudo_detalhado_json,
                       cl.safra,
                       dp.decendio_plantio_zarc,
                       dp.risco_zarc_admissivel
                   FROM agroprods.glebas g
                            JOIN ultimos_atestados am ON g.id_gleba = am.id_gleba AND am.rn = 1
                            JOIN audit.historico_laudos_ambientais_ledger hl ON g.id_gleba = hl.id_gleba AND am.hash_relatorio = hl.hash_bloco
                            JOIN audit.ia_classificacao_cultura_ledger cl ON g.id_gleba = cl.id_gleba AND am.hash_relatorio = cl.hash_bloco
                            JOIN audit.declaracao_gleba_periodo_ledger dp ON g.id_gleba = dp.id_gleba AND am.hash_relatorio = dp.hash_bloco
                   WHERE g.id_produtor = :id_produtor AND cl.safra = :safra
                   ORDER BY hl.data_auditoria DESC
                       LIMIT 1;
                   """)

        result = await self.session.execute(sql, {"id_produtor": id_produtor, "safra": safra})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def consultar_status_pizza_ledger(self, id_produtor: int, safra: str) -> List[Dict[str, Any]]:
        """
        Executa a query baseada na regra de negócio estrita da portaria
        sobre o último bloco consolidado de cada gleba do produtor.
        """
        sql = text("""
                   WITH ultimos_atestados AS (
                       SELECT id_gleba, hash_relatorio,
                              ROW_NUMBER() OVER(PARTITION BY id_gleba ORDER BY data_emissao DESC, id_atestado DESC) as rn
                       FROM audit.atestados_vmg_ledger
                   ),
                        dados_status AS (
                            SELECT
                                g.id_gleba,
                                CASE
                                    WHEN hl.conflito_prodes = FALSE
                                        AND hl.conflito_ibama_icmbio = FALSE
                                        AND hl.conflito_socioambiental = FALSE
                                        AND cl.status_conducao = 'CONDIZENTE'
                                        AND cl.percentual_confianca >= 0.75
                                        THEN 'Conforme'

                                    WHEN hl.conflito_prodes = TRUE
                                        OR hl.conflito_ibama_icmbio = TRUE
                                        OR hl.conflito_comunidades = TRUE
                                        THEN 'Não conforme'

                                    ELSE 'Atenção'
                                    END as status_resultado
                            FROM agroprods.glebas g
                                     JOIN ultimos_atestados am ON g.id_gleba = am.id_gleba AND am.rn = 1
                                     JOIN audit.historico_laudos_ambientais_ledger hl ON g.id_gleba = hl.id_gleba AND am.hash_relatorio = hl.hash_bloco
                                     JOIN audit.ia_classificacao_cultura_ledger cl ON g.id_gleba = cl.id_gleba AND am.hash_relatorio = cl.hash_bloco
                            WHERE g.id_produtor = :id_produtor AND cl.safra = :safra
                        )
                   SELECT status_resultado as status, COUNT(*) as quantidade
                   FROM dados_status
                   GROUP BY status_resultado;
                   """)
        result = await self.session.execute(sql, {"id_produtor": id_produtor, "safra": safra})
        return [dict(row) for row in result.mappings().all()]

    async def buscar_dados_proximas_atividades(self, id_produtor: int, safra: str) -> List[Dict[str, Any]]:
        """
        Busca dados cadastrais das glebas para que o Service calcule de forma
        preditiva e cronológica as datas das janelas automáticas de reanálise da IA.
        """
        sql = text("""
                   SELECT g.id_gleba, g.cultura_declarada,
                          TO_CHAR(g.data_estimada_plantio, 'YYYY-MM-DD') as data_plantio,
                          CASE WHEN hl.conflito_socioambiental = TRUE THEN 'EXIGE_RETIFICACAO' ELSE 'OK' END as status_ambiental
                   FROM agroprods.glebas g
                            LEFT JOIN audit.atestados_vmg_ledger am ON g.id_gleba = am.id_gleba
                            LEFT JOIN audit.historico_laudos_ambientais_ledger hl ON g.id_gleba = hl.id_gleba AND am.hash_relatorio = hl.hash_bloco
                   WHERE g.id_produtor = :id_produtor
                   ORDER BY g.id_gleba DESC
                       LIMIT 3;
                   """)
        result = await self.session.execute(sql, {"id_produtor": id_produtor})
        return [dict(row) for row in result.mappings().all()]