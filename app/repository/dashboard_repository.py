from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import text, Row

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classificacao_model import CertificadosBpa
from app.models.embargos_model import EmbargosOrgaos
from app.models.gleba_model import GlebaModel
from app.models.gleba_model import MunicipioIbge
from app.models.models_ledger import AtestadosVmgLedger
from app.models.notificacao_model import NotificacaoUsuarioModel


class DashboardRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

        self.session = db

    async def cadastrar_gleba_prototipo(self, dados: dict) -> GlebaModel:
        """Insere a gleba mapeando todos os campos do fluxo de 5 etapas do protótipo."""

        sql_query = """
                    INSERT INTO agroprods.glebas
                    (id_produtor, codigo_car, cultura_declarada, geometria, area_hectares,
                     codigo_municipio, data_estimada_plantio, data_criacao)
                    VALUES
                        (:id_produtor, :id_car_vinculado, :cultura_declarada, ST_GeomFromText(:geometria, 4326),
                         :area_hectares, :codigo_municipio, :data_estimada_plantio, NOW())
                        RETURNING id_gleba, id_produtor, codigo_car, cultura_declarada, area_hectares, codigo_municipio, data_estimada_plantio, data_criacao; \
                    """

        result = await self.db.execute(text(sql_query), {
            "id_produtor": dados["id_produtor"],
            "id_car_vinculado": dados["id_car_vinculado"],
            "cultura_declarada": dados["cultura_declarada"],
            "geometria": dados["geometria"],
            "area_hectares": dados["area_hectares"],
            "codigo_municipio": dados["codigo_municipio"],
            "data_estimada_plantio": dados["data_estimada_plantio"]
        })

        row = result.first()
        await self.db.commit()

        # Cria a instância mockando dados extras exigidos pelo DTO de resposta da tela final
        return GlebaModel(
            id_gleba=row.id_gleba,
            id_produtor=row.id_produtor,
            codigo_car=row.codigo_car,
            area_hectares=row.area_hectares,
            cultura_declarada=row.cultura_declarada,
            data_criacao=row.data_criacao
        )

    async def get_kpis(self, safra: str, estado: str = "Todos") -> dict:
        """Calcula os agregados numéricos usando a sintaxe select do SQLAlchemy Async."""
        # 1. Query de Glebas
        stmt_glebas = select(
            func.count(func.distinct(GlebaModel.id_produtor)).label("total_contratos"),
            func.count(GlebaModel.id_gleba).label("total_glebas"),
            func.sum(GlebaModel.area_hectares).label("area_total")
        )

        if estado != "Todos":
            stmt_glebas = stmt_glebas.join(
                MunicipioIbge, MunicipioIbge.codigo_municipio == GlebaModel.codigo_municipio
            ).filter(MunicipioIbge.sigla_uf == estado)

        exec_glebas = await self.db.execute(stmt_glebas)
        glebas_data = exec_glebas.first()

        # 2. Alertas Ativos
        stmt_alertas = select(func.count(EmbargosOrgaos.id)).filter(EmbargosOrgaos.situacao == "Ativo")
        exec_alertas = await self.db.execute(stmt_alertas)
        total_alertas = exec_alertas.scalar() or 0

        # 3. Atestados Emitidos
        stmt_atestados = select(func.count(AtestadosVmgLedger.id_atestado))
        exec_atestados = await self.db.execute(stmt_atestados)
        total_atestados = exec_atestados.scalar() or 0

        return {
            "contratos": {"valor_atual": glebas_data.total_contratos or 0, "variacao_percentual": 8.2, "sufixo": ""},
            "glebas_monitoradas": {"valor_atual": glebas_data.total_glebas or 0, "variacao_percentual": 5.7, "sufixo": ""},
            "area_total": {"valor_atual": float(glebas_data.area_total or 0), "variacao_percentual": 7.1, "sufixo": "ha"},
            "alertas_ativos": {"valor_atual": total_alertas, "variacao_percentual": -12.4, "sufixo": ""},
            "atestados_emitidos": {"valor_atual": total_atestados, "variacao_percentual": 9.2, "sufixo": ""}
        }

    async def get_contratos_por_cultura(self, safra: str) -> List[Dict[str, Any]]:
        """
        Retorna a volumetria de culturas validando se os anos da safra (ex: 2026 e 2027)
        estão compreendidos entre o ano de plantio e colheita do registro.
        """
        # Se receber '2026/2027', busca por ambos os anos na base
        if "/" in safra:
            anos = [int(a) for a in safra.split("/")]
            ano_inicio = str(anos[0])
            ano_fim = str(anos[1])
        else:
            ano_inicio = str(safra)
            ano_fim = str(safra)

        query = text("""
                     SELECT
                         COALESCE("cultura_declarada", 'Outros') AS cultura,
                         COUNT(*)::int AS quantidade
                     FROM "audit"."declaracao_gleba_periodo_ledger"
                     WHERE
                         EXTRACT(YEAR FROM "data_estimada_plantio")::text IN (:ano_inicio, :ano_fim)
                OR EXTRACT(YEAR FROM "data_estimada_colheita")::text IN (:ano_inicio, :ano_fim)
                     GROUP BY "cultura_declarada"
                     ORDER BY quantidade DESC;
                     """)

        result = await self.db.execute(query, {"ano_inicio": ano_inicio, "ano_fim": ano_fim})
        return [
            {
                "cultura": row.cultura,
                "quantidade": row.quantidade
            }
            for row in result.fetchall()
        ]

    async def get_contratos_por_estado(self, safra: str) -> List[Dict[str, Any]]:
        """
        Retorna a volumetria de contratos distribuídos por estado,
        corrigindo o filtro de safra baseado no intervalo de datas do ledger.
        """
        # Extrai os dois anos da string composta (Ex: '2025/2026' -> '2025' e '2026')
        if "/" in safra:
            anos = [int(a) for a in safra.split("/")]
            ano_inicio = str(anos[0])
            ano_fim = str(anos[1])
        else:
            ano_inicio = str(safra)
            ano_fim = str(safra)

        query = text("""
                     SELECT
                         m."sigla_uf" AS estado,
                         COUNT(DISTINCT d."id_declaracao")::int AS quantidade
                     FROM "audit"."declaracao_gleba_periodo_ledger" d
                              JOIN "agroprods"."glebas" g ON d."id_gleba" = g."id_gleba"
                              JOIN "agroprods"."municipio_ibge" m ON g."codigo_municipio" = m."codigo_municipio"
                     WHERE
                         EXTRACT(YEAR FROM d."data_estimada_plantio")::text IN (:ano_inicio, :ano_fim)
                OR EXTRACT(YEAR FROM d."data_estimada_colheita")::text IN (:ano_inicio, :ano_fim)
                     GROUP BY m."sigla_uf"
                     ORDER BY quantidade DESC;
                     """)

        result = await self.db.execute(query, {"ano_inicio": ano_inicio, "ano_fim": ano_fim})
        rows = result.fetchall()

        return [
            {
                "estado": row.estado,
                "quantidade": row.quantidade
            }
            for row in rows
        ]

    async def get_mapa_status_estados(self) -> list:
        """Classificação de risco do mapa de forma assíncrona."""
        stmt = (
            select(
                MunicipioIbge.sigla_uf.label("estado"),
                func.count(NotificacaoUsuarioModel.id).label("total_alertas") # 🟢 Alterado aqui
            )
            .join(GlebaModel, GlebaModel.id_gleba == NotificacaoUsuarioModel.id_gleba) # 🟢 Alterado aqui
            .join(MunicipioIbge, MunicipioIbge.codigo_municipio == GlebaModel.codigo_municipio)
            .group_by(MunicipioIbge.sigla_uf)
        )

        exec_res = await self.db.execute(stmt)
        resultados = exec_res.all()

        status_mapa = []
        for r in resultados:
            status = "Alerta" if r.total_alertas > 50 else ("Atenção" if r.total_alertas > 15 else "Normal")
            status_mapa.append({"estado": r.estado, "status": status})
        return status_mapa

    async def buscar_ultimos_atestados_ledger(self, limite: int = 10) -> List[Row]:
        """Busca os dados imutáveis de atestados emitidos e cruza com dados transacionais na VPS."""
        query = text("""
                     SELECT
                         atestado.id_gleba AS codigo_gleba,
                         g.id_produtor AS id_produtor,
                         muni.nome_municipio AS municipio,
                         atestado.data_emissao AS data,
                         g.area_hectares AS area_ha
                     FROM audit.atestados_vmg_ledger atestado
                              JOIN agroprods.glebas g ON g.id_gleba = atestado.id_gleba
                              JOIN agroprods.municipio_ibge muni ON muni.codigo_municipio = g.codigo_municipio
                     ORDER BY atestado.data_emissao DESC
                         LIMIT :limite;
                     """)

        result = await self.session.execute(query, {"limite": limite})
        return list(result.fetchall())

    async def get_alertas_dashboard(self) -> List[Dict[str, Any]]:
        """
        Contabiliza a volumetria de alertas buscando de forma otimizada
        no novo schema 'audit' a partir dos dados consolidados de auditoria.
        Retorno mantido: List[Dict['tipo_alerta', 'quantidade']]
        """
        query = text("""
                     -- Alertas Fora do ZARC extraídos da declaração consolidada do período
                     SELECT 'Fora do ZARC' AS tipo_alerta, COUNT(*)::int AS quantidade
                     FROM "audit"."declaracao_gleba_periodo_ledger"
                     WHERE "risco_zarc_admissivel"::text NOT ILIKE '%baixo%' 
                    AND "risco_zarc_admissivel"::text NOT ILIKE '%admissivel%'

                     UNION ALL

                     -- Alertas de Embargos extraídos do histórico consolidado de laudos ambientais
                     SELECT 'Embargo IBAMA' AS tipo_alerta, COUNT(*)::int AS quantidade
                     FROM "audit"."historico_laudos_ambientais_ledger"
                     WHERE "conflito_ibama_icmbio" = true OR "conflito_socioambiental" = true

                     UNION ALL

                     -- Alertas de Veranico calculados com base em eventos climáticos gravados
                     SELECT 'Veranico severo' AS tipo_alerta, COUNT(*)::int AS quantidade
                     FROM "agroprods"."notificacao_usuario"
                     WHERE "tipo"::text ILIKE '%veranico%' OR "tipo"::text ILIKE '%severe%';
                     """)

        result = await self.db.execute(query)
        return [
            {
                "tipo_alerta": row.tipo_alerta,
                "quantidade": row.quantidade
            }
            for row in result.fetchall()
        ]

    async def get_atestados_dashboard(self) -> List[Dict[str, Any]]:
        """
        Retorna a listagem detalhada de atestados a partir da tabela centralizada
        'atestados_vmg_ledger' do schema 'audit', eliminando 5 JOINs transacionais.
        Retorno mantido: List[Dict['codigo_gleba', 'produtor', 'municipio', 'data', 'area_ha']]
        """
        query = text("""
                     SELECT
                         'GLB' || LPAD(al."id_gleba"::text, 6, '0') AS codigo_gleba,
                         p."nome" AS produtor,
                         m."nome_municipio" AS municipio,
                         TO_CHAR(al."data_emissao", 'YYYY-MM-DD') AS data,
                         COALESCE(g."area_hectares", 0.0)::float AS area_ha
                     FROM "audit"."atestados_vmg_ledger" al
                              JOIN "agroprods"."glebas" g ON al."id_gleba" = g."id_gleba"
                              JOIN "agroprods"."pessoa" p ON g."id_produtor" = p."id"
                              JOIN "agroprods"."municipio_ibge" m ON g."codigo_municipio" = m."codigo_municipio"
                     WHERE al."status_validacao"::text ILIKE '%valido%' 
               OR al."status_validacao"::text ILIKE '%ativo%'
                     ORDER BY al."data_emissao" DESC;
                     """)

        result = await self.db.execute(query)
        return [
            {
                "codigo_gleba": row.codigo_gleba,
                "produtor": row.produtor,
                "municipio": row.municipio,
                "data": row.data,
                "area_ha": row.area_ha
            }
            for row in result.fetchall()
        ]

    async def get_heatmap_dashboard(self) -> List[Dict[str, Any]]:
        """
        Retorna as coordenadas reais calculadas a partir da coluna 'coordenada'
        e define o status baseado no índice NDVI de saúde das plantas.
        """
        query = text("""
                     SELECT
                         ST_Y("coordenada")::float AS latitude,
                         ST_X("coordenada")::float AS longitude,
                         CASE
                             WHEN "saude_plantas_ndvi" < 0.40 THEN 'vermelho'
                             WHEN "saude_plantas_ndvi" BETWEEN 0.40 AND 0.65 THEN 'amarelo'
                             ELSE 'verde'
                             END AS status
                     FROM "agroprods"."propriedades_solo_grid"
                     WHERE "coordenada" IS NOT NULL
                         LIMIT 1000;
                     """)

        result = await self.db.execute(query)
        return [
            {
                "latitude": row.latitude,
                "longitude": row.longitude,
                "status": row.status
            }
            for row in result.fetchall()
        ]

    async def get_metricas_safra(self, safra: str, estado: str = "Todos") -> Dict[str, Any]:
        """
        Calcula os volumes agregados baseados na tabela glebas e atestados_vmg_ledger.
        Corrige a sintaxe eliminando o operador 'AS text' da cláusula WHERE e adotando '::text'.
        """
        filtro_estado = ""
        if estado and estado != "Todos":
            filtro_estado = f"AND m.\"sigla_uf\" = '{estado}'"

        query = text(f"""
            SELECT
                -- Total de Contratos (mapeados pelas classificações da safra)
                COUNT(DISTINCT cc."id_classificacao")::int AS total_contratos,
                -- Glebas agrícolas monitoradas na safra
                COUNT(DISTINCT g."id_gleba")::int AS total_glebas,
                -- Área total monitorada
                COALESCE(SUM(g."area_hectares"), 0)::float AS area_total,
                -- Alertas ativos gerais do sistema
                (SELECT COUNT(*)::int FROM "agroprods"."notificacao_usuario" WHERE "status"::text ILIKE '%ativo%') AS alertas_ativos,
                -- Atestados emitidos gerais do sistema
                (SELECT COUNT(*)::int FROM audit.atestados_vmg_ledger) AS atestados_emitidos,
                -- QUANTIDADE DE PRODUTORES CORRIGIDA (Adicionado FROM e filtro por tipo)
                (SELECT COUNT(DISTINCT id)::int FROM agroprods.pessoa WHERE tipo = 'PRODUTOR') AS produtores_ativos
            FROM audit.ia_classificacao_cultura_ledger cc
            JOIN agroprods.glebas g  ON cc.id_gleba = g.id_gleba
            JOIN "agroprods"."municipio_ibge" m ON g."codigo_municipio" = m."codigo_municipio"
            WHERE cc."safra" = :safra {filtro_estado};
        """)

        result = await self.db.execute(query, {"safra": safra})
        row = result.fetchone()

        if not row:
            return {
                "total_contratos": 0, "total_glebas": 0, "area_total": 0.0,
                "alertas_ativos": 0, "atestados_emitidos": 0, "produtores_ativos": 0
            }

        return {
            "total_contratos": row.total_contratos,
            "total_glebas": row.total_glebas,
            "area_total": row.area_total,
            "alertas_ativos": row.alertas_ativos,
            "atestados_emitidos": row.atestados_emitidos,
            "produtores_ativos": row.produtores_ativos
        }

    async def get_atestados_dashboard(self) -> List[Dict[str, Any]]:
        """
        Retorna a lista de atestados aplicando os JOINs com os campos exatos da imagem:
        certificados_bpa (id, produtor_id) -> pessoa (id)
        certificados_bpa_glebas (id_certificado, id_gleba) -> glebas (id_gleba)
        """
        query = text("""
                     SELECT
                         'GLB' || LPAD(g."id_gleba"::text, 6, '0') AS codigo_gleba,
                         p."nome" AS produtor,
                         m."nome_municipio" AS municipio,
                         TO_CHAR(c."data_emissao", 'YYYY-MM-DD') AS data,
                         g."area_hectares"::float AS area_ha
                     FROM "agroprods"."certificados_bpa" c
                              JOIN "agroprods"."certificados_bpa_glebas" cbg ON c."id" = cbg."id_certificado"
                              JOIN "agroprods"."glebas" g ON cbg."id_gleba" = g."id_gleba"
                              JOIN "agroprods"."pessoa" p ON c."produtor_id" = p."id"
                              JOIN "agroprods"."municipio_ibge" m ON g."codigo_municipio" = m."codigo_municipio"
                     WHERE c."status" ILIKE '%ativo%' OR c."status" ILIKE '%valido%'
                     ORDER BY c."data_emissao" DESC;
                     """)

        result = await self.db.execute(query)
        return [
            {
                "codigo_gleba": row.codigo_gleba,
                "produtor": row.produtor,
                "municipio": row.municipio,
                "data": row.data,
                "area_ha": row.area_ha
            }
            for row in result.fetchall()
        ]

    async def get_heatmap_dashboard(self) -> List[Dict[str, Any]]:
        """
        Extrai as coordenadas da coluna 'coordenada' usando PostGIS ST_X/ST_Y
        e define o status de risco usando a coluna 'saude_plantas_ndvi'.
        """
        query = text("""
                     SELECT
                         ST_Y("coordenada")::float AS latitude,
                         ST_X("coordenada")::float AS longitude,
                         CASE
                             WHEN "saude_plantas_ndvi" < 0.45 THEN 'vermelho'
                             ELSE 'verde'
                             END AS status
                     FROM "agroprods"."propriedades_solo_grid"
                     WHERE "coordenada" IS NOT NULL
                         LIMIT 500;
                     """)

        result = await self.db.execute(query)
        return [{"latitude": row.latitude, "longitude": row.longitude, "status": row.status} for row in result.fetchall()]

    async def get_gleba_timeline(self, id_gleba: int) -> List[Dict[str, Any]]:
        query = text("""
                     SELECT 'Declaração' AS etapa, 'Período declaratório registrado no ledger' AS detalhe, "data_registro" AS data_log
                     FROM "audit"."declaracao_gleba_periodo_ledger" WHERE "id_gleba" = :id_gleba

                     UNION ALL

                     SELECT 'Análise Satélite' AS etapa, 'Classificação de cultura processada por IA' AS detalhe, "data_analise" AS data_log
                     FROM "audit"."ia_classificacao_cultura_ledger" WHERE "id_gleba" = :id_gleba

                     UNION ALL

                     SELECT 'Certificação' AS etapa, 'Atestado emitido e assinado digitalmente' AS detalhe, "data_emissao" AS data_log
                     FROM "audit"."atestados_vmg_ledger" WHERE "id_gleba" = :id_gleba

                     ORDER BY data_log ASC;
                     """)
        result = await self.db.execute(query, {"id_gleba": id_gleba})
        return [{
            "etapa": r.etapa,
            "detalhe": r.detalhe,
            "data": r.data_log.strftime("%Y-%m-%d %H:%M:%S") if r.data_log else None
        } for r in result.fetchall()]

    async def get_ia_analise_ambiental(self, safra: str) -> Dict[str, Any]:
        """
        Retorna os percentuais de conformidade ambiental baseados nos laudos do ledger.
        """
        query = text("""
                     SELECT
                         COUNT(CASE WHEN "conflito_ibama_icmbio" = false AND "conflito_socioambiental" = false THEN 1 END)::int AS conforme,
                         COUNT(CASE WHEN "conflito_socioambiental" = true AND "conflito_ibama_icmbio" = false THEN 1 END)::int AS atencao,
                         COUNT(CASE WHEN "conflito_ibama_icmbio" = true THEN 1 END)::int AS nao_conforme,
                         COUNT(*)::int AS total
                     FROM "audit"."historico_laudos_ambientais_ledger";
                     """)
        result = await self.db.execute(query)
        row = result.fetchone()

        if not row or row.total == 0:
            return {"conforme_pct": 100, "atencao_pct": 0, "nao_conforme_pct": 0}

        return {
            "conforme_pct": round((row.conforme / row.total) * 100),
            "atencao_pct": round((row.atencao / row.total) * 100),
            "nao_conforme_pct": round((row.nao_conforme / row.total) * 100)
        }

    async def get_ia_classificacao_culturas(self, safra: str) -> Dict[str, Any]:
        """
        Calcula a acurácia média e a volumetria das culturas identificadas por IA.
        """
        # Query para métricas gerais
        query_metricas = text("""
                              SELECT
                                  COALESCE(AVG("percentual_confianca"), 0)::float AS acuracia_media,
                                  COUNT(DISTINCT "id_gleba")::int AS total_glebas
                              FROM "audit"."ia_classificacao_cultura_ledger"
                              WHERE "safra" = :safra;
                              """)
        res_metricas = await self.db.execute(query_metricas, {"safra": safra})
        row_m = res_metricas.fetchone()

        # Query para a distribuição do top culturas
        query_top = text("""
                         SELECT
                             COALESCE("cultura_identificada", 'Outros') AS cultura,
                             COUNT(*)::int AS quantidade
                         FROM "audit"."ia_classificacao_cultura_ledger"
                         WHERE "safra" = :safra
                         GROUP BY "cultura_identificada"
                         ORDER BY quantidade DESC;
                         """)
        res_top = await self.db.execute(query_top, {"safra": safra})

        total_glebas = row_m.total_glebas if row_m else 0
        top_culturas = []
        for r in res_top.fetchall():
            pct = round((r.quantidade / total_glebas) * 100) if total_glebas > 0 else 0
            top_culturas.append({"nome": r.cultura, "percentual": pct})

        return {
            "acuracia_media": round(row_m.acuracia_media, 1) if row_m else 0.0,
            "total_glebas_analisadas": total_glebas,
            "top_culturas": top_culturas
        }

    async def get_ia_produtividade_estimada(self, safra: str) -> Dict[str, Any]:
        """
        Retorna a média geral de sacas por hectare, área total e volume estimado pela IA
        vinculando a tabela de auditoria com a tabela física de glebas para obter a área.
        """
        query = text("""
                     SELECT
                         COALESCE(AVG(p."produtividade_ia_sacas_ha"), 0)::float AS media_sacas,
                         COALESCE(SUM(g."area_hectares"), 0)::float AS area_total,
                         COALESCE(SUM(p."volume_comercializar_declarado"), 0)::float AS volume_total
                     FROM "audit"."ia_estimativa_produtividade_ledger" p
                              JOIN "agroprods"."glebas" g ON p."id_gleba" = g."id_gleba"
                     WHERE p."safra" = :safra;
                     """)

        result = await self.db.execute(query, {"safra": safra})
        row = result.fetchone()

        if not row:
            return {
                "produtividade_media_sacas": 0,
                "area_estimada_ha": 0,
                "volume_estimado_sacas": 0
            }

        return {
            "produtividade_media_sacas": round(row.media_sacas),
            "area_estimada_ha": round(row.area_total),
            "volume_estimado_sacas": round(row.volume_total)
        }

    async def obter_dados_climaticos_globais_por_estado(self, data_limite: datetime, uf: Optional[str] = None) -> List[Any]:
        """
        Query meteorológica regionalizada: Consolida as médias do INMET agrupadas por Estado (UF),
        trazendo APENAS as regiões que possuem glebas agrícolas cadastradas na base.
        """
        sql_base = """
                   SELECT
                       UPPER(TRIM(e.uf)) AS estado_uf,
                       COALESCE(SUM(s.chuva_mm), 0) AS total_chuva,
                       COALESCE(AVG(s.temp_c), 0) AS avg_temperatura,
                       COALESCE(AVG(s.vento_velocidade), 0) AS avg_vento,
                       COUNT(*) FILTER (WHERE s.chuva_mm = 0) AS dias_secos
                   FROM agroprods.series_climaticas_diarias s
                            JOIN agroprods.estacoes_inmet e ON e.id = s.id_estacao
                   WHERE s.data >= :data_limite
                     AND UPPER(e.status) = 'OPERANTE'

                     -- REGRA: Filtra apenas os estados que possuem feições geográficas de glebas ativas
                     AND UPPER(TRIM(e.uf)) IN (
                       SELECT DISTINCT UPPER(TRIM(m.sigla_uf))
                       FROM agroprods.municipio_ibge m
                                JOIN agroprods.glebas g ON g.codigo_municipio = m.codigo_municipio
                       WHERE g.codigo_municipio IS NOT NULL
                   ) \
                   """

        parametros = {"data_limite": data_limite}

        if uf and uf.strip() and uf.upper() != "TODOS":
            sql_base += " AND UPPER(TRIM(e.uf)) = :uf "
            parametros["uf"] = uf.strip().upper()

        sql_base += """
            GROUP BY UPPER(TRIM(e.uf))
            ORDER BY estado_uf ASC;
        """

        resultado = await self.db.execute(text(sql_base), parametros)
        return resultado.all()

    async def buscar_eventos_climaticos_ledger(self, limite_meses: int = 60) -> List[Row]:
        """Consulta as tabelas imutáveis do Ledger consolidando a série histórica total de 60 meses."""
        data_limite = (datetime.now(timezone.utc) - timedelta(days=limite_meses * 30)).replace(tzinfo=None)

        query = text("""
                     SELECT
                         COALESCE(laudo.laudo_detalhado_json->>'evento_critico', 'Dias sem chuva') AS evento,
                         muni.nome_municipio AS municipio,
                         laudo.data_auditoria AS data,
                         laudo.conflito_socioambiental AS conflito_socioambiental,
                         laudo.conflito_prodes AS conflito_prodes,
                         COUNT(DISTINCT laudo.id_gleba) AS glebas_afetadas
                     FROM audit.historico_laudos_ambientais_ledger laudo
                              JOIN agroprods.glebas g ON g.id_gleba = laudo.id_gleba
                              JOIN agroprods.municipio_ibge muni ON muni.codigo_municipio = g.codigo_municipio
                     WHERE laudo.data_auditoria >= :data_limite
                     GROUP BY
                         laudo.laudo_detalhado_json->>'evento_critico',
                         muni.nome_municipio,
                         laudo.data_auditoria,
                         laudo.conflito_socioambiental,
                         laudo.conflito_prodes
                     ORDER BY laudo.data_auditoria DESC
                         LIMIT 10;
                     """)

        result = await self.session.execute(query, {"data_limite": data_limite})
        return list(result.fetchall())
