from aiohttp import payload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, case, literal_column, Numeric
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from fastapi import HTTPException, status

from app.dto.produtor.dashboard_produtor_schema import ClimaResumoResponse, ProdutividadeEstimadaResponse, \
    SerieProdutividadeMensal
from app.models.classificacao_model import SerieClimaticaDiaria, EstacaoInmet
from app.models.gleba_model import GlebaModel
from app.models.models import Gleba
from app.models.models_ledger import IaEstimativaProdutividadeLedger, DeclaracaoGlebaPeriodoLedger


class DashboardProdutorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.db = session

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
                   ),
                        dados_base AS (
                            SELECT
                                g.area_hectares,
                                hl.conflito_socioambiental,
                                hl.conflito_prodes,
                                hl.conflito_ibama_icmbio,
                                hl.conflito_comunidades,
                                hl.laudo_detalhado_json,
                                cl.safra,
                                dp.decendio_plantio_zarc,
                                dp.risco_zarc_admissivel,
                                hl.data_auditoria,

                                EXISTS (
                                    SELECT 1
                                    FROM agroprods.zarc_zoneamento AS zz
                                    WHERE zz.municipio_ibge::VARCHAR = g.codigo_municipio::VARCHAR
                                        AND UPPER(zz.cultura) = UPPER(cl.cultura_identificada)
                                        AND zz.decendio_plantio::INT = dp.decendio_plantio_zarc::INT
                                        AND zz.safra::VARCHAR = SPLIT_PART(cl.safra, '/', 1)::VARCHAR
                                ) AS informacao_zarc
                            FROM agroprods.glebas g
                                     JOIN ultimos_atestados am ON g.id_gleba = am.id_gleba AND am.rn = 1
                                     JOIN audit.historico_laudos_ambientais_ledger hl ON g.id_gleba = hl.id_gleba AND am.hash_relatorio = hl.hash_bloco
                                     JOIN audit.ia_classificacao_cultura_ledger cl ON g.id_gleba = cl.id_gleba AND am.hash_relatorio = cl.hash_bloco
                                     JOIN audit.declaracao_gleba_periodo_ledger dp ON g.id_gleba = dp.id_gleba AND am.hash_relatorio = dp.hash_bloco
                            WHERE g.id_produtor = :id_produtor AND cl.safra = :safra
                        ),
                        regras_mapeadas AS (
                            SELECT
                                db.safra,
                                c.nome,
                                c.conflito,
                                p.pct_padrao AS pct,
                                p.redutor_padrao AS redutor
                            FROM dados_base db
                                     CROSS JOIN LATERAL (
                                VALUES
                                    ('APP', db.conflito_socioambiental::BOOLEAN),
                                    ('Reserva Legal', db.conflito_socioambiental::BOOLEAN),
                                    ('Vegetação Nativa', db.conflito_socioambiental::BOOLEAN),
                                    ('PRODES', db.conflito_prodes::BOOLEAN),
                                    ('Embargo IBAMA', db.conflito_ibama_icmbio::BOOLEAN),
                                    ('Embargo ICMBio', db.conflito_ibama_icmbio::BOOLEAN),
                                    ('Unidades de Conservação', db.conflito_socioambiental::BOOLEAN),
                                    ('Terras Indígenas', db.conflito_comunidades::BOOLEAN),
                                    ('Quilombolas', db.conflito_comunidades::BOOLEAN),
                                    ('ZARC', CASE WHEN CAST(db.risco_zarc_admissivel AS NUMERIC) > 40.0 THEN true ELSE false END)
                                    ) AS c(nome, conflito)
                                     LEFT JOIN agroprods.parametros_conformidade p
                                               ON p.criterio_nome = c.nome
                                                   AND p.safra::VARCHAR = db.safra::VARCHAR
                       )
                   SELECT
                       db.area_hectares,
                       db.conflito_socioambiental,
                       db.conflito_prodes,
                       db.conflito_ibama_icmbio,
                       db.conflito_comunidades,
                       db.laudo_detalhado_json,
                       db.safra,
                       db.decendio_plantio_zarc,
                       db.risco_zarc_admissivel,
                       db.informacao_zarc,

                       -- RETORNO FORMATADO E COMPATÍVEL COM SEU DICIONÁRIO PYTHON
                       (
                           SELECT json_agg(json_build_object(
                                   'nome', rm.nome,
                                   'conflito', rm.conflito,
                                   'pct', rm.pct,
                                   'redutor', rm.redutor
                                           ))
                           FROM regras_mapeadas rm
                       ) AS criterios_mapeados
                   FROM dados_base db
                   ORDER BY db.data_auditoria DESC
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

    async def obter_metricas_consolidadas_ia(self, id_produtor: int, safra: str) -> Optional[Tuple[Any, Any, Any]]:
        """
        Query corrigida utilizando os modelos do ORM SQLAlchemy diretamente.
        """
        query = (
            select(
                func.sum(func.coalesce(func.cast(Gleba.area_hectares, func.Numeric), 0)).label("area_total"),
                func.sum(func.coalesce(IaEstimativaProdutividadeLedger.volume_comercializar_declarado, 0)).label("volume_total"),
                func.avg(func.coalesce(func.cast(IaEstimativaProdutividadeLedger.produtividade_ia_sacas_ha, func.Numeric), 0)).label("media_produtividade")
            )
            .join(
                DeclaracaoGlebaPeriodoLedger,
                DeclaracaoGlebaPeriodoLedger.id_gleba == Gleba.id_gleba
            )
            .join(
                IaEstimativaProdutividadeLedger,
                IaEstimativaProdutividadeLedger.id_gleba == Gleba.id_gleba
            )
            .where(
                and_(
                    DeclaracaoGlebaPeriodoLedger.id_produtor == id_produtor,
                    IaEstimativaProdutividadeLedger.safra == safra
                )
            )
        )
        resultado = await self.db.execute(query)
        return resultado.first()

    async def obter_metricas_consolidadas_ia(self, id_produtor: int, safra: str):
        """
        Query corrigida substituindo func.Numeric por Numeric puro.
        """
        query = (
            select(
                # CORREÇÃO AQUI: Mudança de func.Numeric para Numeric
                func.sum(func.coalesce(func.cast(GlebaModel.area_hectares, Numeric), 0)).label("area_total"),
                func.sum(func.coalesce(IaEstimativaProdutividadeLedger.volume_comercializar_declarado, 0)).label("volume_total"),
                func.avg(func.coalesce(func.cast(IaEstimativaProdutividadeLedger.produtividade_ia_sacas_ha, Numeric), 0)).label("media_produtividade")
            )
            .join(
                DeclaracaoGlebaPeriodoLedger,
                DeclaracaoGlebaPeriodoLedger.id_gleba == GlebaModel.id_gleba
            )
            .join(
                IaEstimativaProdutividadeLedger,
                IaEstimativaProdutividadeLedger.id_gleba == GlebaModel.id_gleba
            )
            .where(
                and_(
                    DeclaracaoGlebaPeriodoLedger.id_produtor == id_produtor,
                    IaEstimativaProdutividadeLedger.safra == safra
                )
            )
        )
        resultado = await self.db.execute(query)
        return resultado.first()

    async def obter_serie_mensal_produtividade(self, id_produtor: int, safra: str) -> List[Any]:
        """
        Query de série mensal corrigida: Utiliza 'date_trunc' de forma simétrica no select,
        group_by e order_by para neutralizar erros de agrupamento do PostgreSQL.
        """
        # Isola a data truncada por mês. Isso garante compilação síncrona idêntica em todas as cláusulas SQL
        expressao_mes_tronco = func.date_trunc('month', IaEstimativaProdutividadeLedger.data_calculo)

        query = (
            select(
                # Formata o tronco da data para a abreviação do mês (Ex: 'Jan', 'Fev'...)
                func.to_char(expressao_mes_tronco, 'Mon').label("mes"),
                func.avg(func.coalesce(func.cast(IaEstimativaProdutividadeLedger.produtividade_ia_sacas_ha, Numeric), 0)).label("media_mes")
            )
            .join(GlebaModel, GlebaModel.id_gleba == IaEstimativaProdutividadeLedger.id_gleba)
            .join(DeclaracaoGlebaPeriodoLedger, DeclaracaoGlebaPeriodoLedger.id_gleba == GlebaModel.id_gleba)
            .where(
                and_(
                    DeclaracaoGlebaPeriodoLedger.id_produtor == id_produtor,
                    IaEstimativaProdutividadeLedger.safra == safra
                )
            )
            # Agrupa unicamente pela expressão do tronco da data
            .group_by(expressao_mes_tronco)
            # Ordena de maneira sequencial e cronológica pelo tronco da data
            .order_by(expressao_mes_tronco)
        )

        resultado = await self.db.execute(query)
        return resultado.all()


    async def obter_dados_meteorologicos_por_municipios_produtor(self, id_produtor: int, data_limite: datetime) -> Optional[Any]:
        """
        Query meteorológica regionalizada: Filtra as séries climáticas diárias do INMET
        com base estrita nos códigos IBGE dos municípios onde o produtor possui glebas registradas.
        """
        sql_query = text("""
                         SELECT
                             COALESCE(SUM(s.chuva_mm), 0) AS total_chuva,
                             COALESCE(AVG(s.temp_c), 0) AS avg_temperatura,
                             COALESCE(AVG(s.vento_velocidade), 0) AS avg_vento,
                             COUNT(*) FILTER (WHERE s.chuva_mm = 0) AS dias_secos
                         FROM agroprods.series_climaticas_diarias s
                                  JOIN agroprods.estacoes_inmet e ON e.id = s.id_estacao
                         WHERE s.data >= :data_limite
                           AND UPPER(e.status) = 'OPERANTE'
                           -- Nova regra de negócio: Filtra apenas pelas estações localizadas nos municípios do produtor
                           AND e.uf IN (
                             SELECT DISTINCT sigla_uf
                             FROM agroprods.municipio_ibge
                             WHERE codigo_municipio IN (
                                 SELECT codigo_municipio
                                 FROM agroprods.glebas
                                 WHERE id_produtor = :id_produtor AND codigo_municipio IS NOT NULL
                             )
                         )
                         """)

        # Executa injetando ambos os parâmetros de busca assíncrona com proteção contra SQL Injection
        resultado = await self.db.execute(
            sql_query,
            {"id_produtor": id_produtor, "data_limite": data_limite}
        )
        return resultado.first()