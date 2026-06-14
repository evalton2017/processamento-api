# app/repository/compliance_repository.py
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class ComplianceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def verificar_restricoes_portaria(self, id_gleba: int, raio_metros: float = 500.0) -> Dict[str, Any]:
        """
        Executa validações espaciais unificadas baseadas na portaria Agro Brasil + Sustentável.
        Aplica cruzamentos na área delimitada (Gleba) e por raio com base no centroide.
        """
        query = text("""
                     WITH gleba_info AS (
                         -- Recupera a geometria e calcula o centroide original da gleba
                         SELECT geometria, ST_Centroid(geometria) AS centroide
                         FROM agroprods.glebas
                         WHERE id_gleba = :id_gleba
                     ),
                          gleba_raio AS (
                              -- Gera o buffer de amortecimento do centroide (item 2.1-b) usando cast para geography
                              SELECT ST_Buffer(centroide::geography, :raio_metros)::geometry AS zona_raio
                              FROM gleba_info
                          )
                     SELECT
                         -- CATEGORIA 1: CAR Feições Ambientais (Itens a, b, c, d, f, g)
                         EXISTS(SELECT 1 FROM agroprods.car_feicoes_ambientais f, gleba_info g WHERE ST_Intersects(g.geometria, f.geom) AND f.tipo_feicao = 'APP') AS intersecao_app,
                         EXISTS(SELECT 1 FROM agroprods.car_feicoes_ambientais f, gleba_info g WHERE ST_Intersects(g.geometria, f.geom) AND f.tipo_feicao = 'BANHADO') AS intersecao_banhado,
                         EXISTS(SELECT 1 FROM agroprods.car_feicoes_ambientais f, gleba_info g WHERE ST_Intersects(g.geometria, f.geom) AND f.tipo_feicao = 'MANGUEZAL') AS intersecao_manguezal,
                         EXISTS(SELECT 1 FROM agroprods.car_feicoes_ambientais f, gleba_info g WHERE ST_Intersects(g.geometria, f.geom) AND f.tipo_feicao = 'RESERVA_LEGAL') AS intersecao_reserva_legal,
                         EXISTS(SELECT 1 FROM agroprods.car_feicoes_ambientais f, gleba_info g WHERE ST_Intersects(g.geometria, f.geom) AND f.tipo_feicao = 'USO_RESTRITO') AS intersecao_uso_restrito,
                         EXISTS(SELECT 1 FROM agroprods.car_feicoes_ambientais f, gleba_info g WHERE ST_Intersects(g.geometria, f.geom) AND f.tipo_feicao = 'VEGETACAO_NATIVA') AS intersecao_vegetacao_nativa,

                         -- CATEGORIA 2: Patrimônio Histórico (Item e) - Validação dupla: Gleba e Raio Centroide
                         EXISTS(SELECT 1 FROM agroprods.sitios_arqueologicos s, gleba_info g WHERE ST_Intersects(g.geometria, s.geom)) AS intersecao_arqueologico,
                         EXISTS(SELECT 1 FROM agroprods.sitios_arqueologicos s, gleba_raio r WHERE ST_Intersects(r.zona_raio, s.geom)) AS raio_arqueologico,

                         -- CATEGORIA 3: Embargos (Itens i, j)
                         EXISTS(SELECT 1 FROM agroprods.embargos_orgaos e, gleba_info g WHERE ST_Intersects(g.geometria, e.geom) AND e.orgao_emissor = 'IBAMA' AND e.situacao = 'ATIVO') AS embargo_ibama,
                         EXISTS(SELECT 1 FROM agroprods.embargos_orgaos e, gleba_info g WHERE ST_Intersects(g.geometria, e.geom) AND e.orgao_emissor = 'ICMBIO' AND e.situacao = 'ATIVO') AS embargo_icmbio,

                         -- CATEGORIA 4: Geografia Social e Fundiária (Itens k, l, m)
                         EXISTS(SELECT 1 FROM agroprods.assentamentos_incra a, gleba_info g WHERE ST_Intersects(g.geometria, a.geom)) AS conflito_assentamento,
                         EXISTS(SELECT 1 FROM agroprods.areas_indigenas_funai ai, gleba_info g WHERE ST_Intersects(g.geometria, ai.geom)) AS conflito_indigena,
                         EXISTS(SELECT 1 FROM agroprods.territorios_quilombolas_incra tq, gleba_info g WHERE ST_Intersects(g.geometria, tq.geom)) AS conflito_quilombola,

                         -- CATEGORIA 5: Proteção Ambiental (Item o) - Filtrado por tipo de camada
                         EXISTS(SELECT 1 FROM agroprods.unidades_conservacao_icmbio uc, gleba_info g WHERE ST_Intersects(g.geometria, uc.geom) AND uc.tipo_camada = 'UNIDADE_CONSERVACAO') AS intersecao_uc,
                         EXISTS(SELECT 1 FROM agroprods.unidades_conservacao_icmbio uc, gleba_raio r WHERE ST_Intersects(r.zona_raio, uc.geom) AND uc.tipo_camada = 'ZONA_AMORTECIMENTO') AS raio_zona_amortecimento,

                         -- CATEGORIA 6: Monitoramento de Desmatamento (Item h)
                         EXISTS(SELECT 1 FROM agroprods.analise_prodes p, gleba_info g WHERE ST_Intersects(g.geometria, p.geom)) AS conflito_prodes
                     """)

        result = await self.session.execute(query, {"id_gleba": id_gleba, "raio_metros": raio_metros})
        rec = result.mappings().first()

        # Consolidação da regra de negócio: qualquer interseção crítica gera um bloqueio socioambiental
        conflito_critico = any([
            rec["intersecao_app"], rec["intersecao_banhado"], rec["intersecao_manguezal"],
            rec["embargo_ibama"], rec["embargo_icmbio"], rec["conflito_indigena"],
            rec["conflito_quilombola"], rec["intersecao_uc"], rec["conflito_prodes"]
        ])

        return {
            "conflito_socioambiental": bool(conflito_critico),
            "laudo_detalhado": dict(rec)
        }
