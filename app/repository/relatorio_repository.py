# app/repositories/relatorio_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional

class RelatorioRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def obter_dados_atestado_por_gleba(self, id_gleba: int) -> Optional[dict]:
        """
        Busca os dados consolidados do atestado mais recente de uma gleba específica,
        cruzando as tabelas transacionais com as tabelas imutáveis do esquema audit.
        """
        query = text("""
                     SELECT
                         -- Cabeçalho & Gleba (Base Transacional)
                         g.id_gleba,
                         g.nome_gleba,
                         g.area_hectares,
                         g.codigo_car,
                         ST_AsText(g.geometria) AS coordenadas_raw,
                         g.data_criacao,
                         TO_CHAR(g.data_criacao, 'DD/MM/YYYY') AS dt_cadastro_gleba,
                         m.nome_municipio || ' / ' || m.sigla_uf AS municipio_uf,
                         -- Último Atestado Emitido (Ledger)
                         atl.id_atestado,
                         TO_CHAR(atl.data_emissao, 'DD/MM/YYYY') AS dt_emissao,
                         TO_CHAR(atl.data_emissao + INTERVAL '30 days', 'DD/MM/YYYY') AS dt_fim,
                         atl.data_emissao,
                         atl.status_validacao,
                         atl.estimativa_produtividade_sacas,
                         atl.hash_relatorio,
                         -- Última Declaração de Período/Safra (Ledger)
                         d_led.cultura_declarada AS cultura_principal,
                         d_led.possui_certificado_bpa,
                         d_led.decendio_plantio_zarc,
                         d_led.risco_zarc_admissivel,
                         d_led.data_estimada_plantio,
                         d_led.data_estimada_colheita,
                         TO_CHAR(d_led.data_estimada_plantio, 'DD/MM/YYYY') AS dt_estimada_plantio,
                         TO_CHAR(d_led.data_estimada_colheita, 'DD/MM/YYYY') AS dt_estimada_colheita,
                         -- Última Classificação de Imagem/Safra da IA (Ledger)
                         ia_led.safra,
                         ia_led.status_conducao,
                         -- Último Monitoramento de Produtividade IA (Ledger)
                         ia_prod_led.volume_comercializar_declarado,
                         ia_prod_led.produtividade_ia_sacas_ha,
                         -- Última Análise Socioambiental (Ledger)
                         laudo_led.conflito_socioambiental,
                         laudo_led.conflito_prodes,
                         laudo_led.conflito_ibama_icmbio,
                         laudo_led.conflito_comunidades,

                         -- VALIDAÇÃO ZARC SOLICITADA
                         CASE
                             WHEN EXISTS (
                                 SELECT 1
                                 FROM agroprods.zarc_zoneamento AS zz
                                 WHERE zz.municipio_ibge = g.codigo_municipio
                                   AND UPPER(zz.cultura) = UPPER(ia_led.cultura_identificada)
                                   -- Caso queira usar o decendio da declaração:
                                   AND zz.decendio_plantio = d_led.decendio_plantio_zarc
                                   AND zz.safra = CAST(SPLIT_PART(ia_led.safra, '/', 1) AS VARCHAR)
                             ) THEN 'Aprovado'
                             ELSE 'FORA_ZARC'
                             END AS validacao_zarc

                     FROM agroprods.glebas g
                              LEFT JOIN agroprods.municipio_ibge m ON m.codigo_municipio = g.codigo_municipio
                         -- Busca o atestado emitido mais recente para esta gleba
                              LEFT JOIN (
                         SELECT DISTINCT ON (id_gleba) *
                         FROM audit.atestados_vmg_ledger
                         WHERE id_gleba = :id_gleba
                         ORDER BY id_gleba, data_emissao DESC
                     ) atl ON atl.id_gleba = g.id_gleba
                         -- Subqueries otimizadas para trazer a última linha de cada ledger da gleba
                              LEFT JOIN (
                         SELECT DISTINCT ON (id_gleba) *
                         FROM audit.declaracao_gleba_periodo_ledger
                         WHERE id_gleba = :id_gleba
                         ORDER BY id_gleba, data_registro DESC
                     ) d_led ON d_led.id_gleba = g.id_gleba
                              LEFT JOIN (
                         SELECT DISTINCT ON (id_gleba) *
                         FROM audit.ia_classificacao_cultura_ledger
                         WHERE id_gleba = :id_gleba
                         ORDER BY id_gleba, data_analise DESC
                     ) ia_led ON ia_led.id_gleba = g.id_gleba
                              LEFT JOIN (
                         SELECT DISTINCT ON (id_gleba) *
                         FROM audit.historico_laudos_ambientais_ledger
                         WHERE id_gleba = :id_gleba
                         ORDER BY id_gleba, data_auditoria DESC
                     ) laudo_led ON laudo_led.id_gleba = g.id_gleba
                              LEFT JOIN (
                         SELECT DISTINCT ON (id_gleba) *
                         FROM audit.ia_estimativa_produtividade_ledger
                         WHERE id_gleba = :id_gleba
                         ORDER BY id_gleba, data_calculo DESC
                     ) ia_prod_led ON ia_prod_led.id_gleba = g.id_gleba
                     WHERE g.id_gleba = :id_gleba;
                     """)

        result = await self.db.execute(query, {"id_gleba": id_gleba})
        row = result.mappings().first()
        return dict(row) if row and row.get("id_gleba") is not None else None
