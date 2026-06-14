from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, desc

from app.models.models import ClassificacaoCultura


# =========================================================
# BPA
# =========================================================
class BpaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def possui_certificado_valido(self, id_produtor: int) -> bool:
        query = text("""
                     SELECT EXISTS (
                         SELECT 1
                         FROM agroprods.certificados_bpa
                         WHERE produtor_id = :id_produtor
                           AND status = 'ATIVO'
                           AND data_validade >= CURRENT_DATE
                     )
                     """)

        result = await self.session.execute(query, {"id_produtor": id_produtor})
        return bool(result.scalar())


# =========================================================
# SOLO
# =========================================================
class SoloRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def nitrogenio_medio_gleba(self, id_gleba: int) -> float:
        query = text("""
                     SELECT COALESCE(AVG(s.nitrogenio_nivel), 45.0)
                     FROM agroprods.propriedades_solo_grid s
                     WHERE s.id_gleba = :id_gleba
                     """)

        result = await self.session.execute(query, {"id_gleba": id_gleba})
        return float(result.scalar() or 45.0)

    async def obter_gleba(self, id_gleba: int):
        query = text("""
                     SELECT id_gleba, id_produtor, codigo_car, cultura_declarada,
                            area_hectares, data_estimada_plantio, data_criacao,
                            ST_AsText(geometria) as geometria
                     FROM agroprods.glebas
                     WHERE id_gleba = :id_gleba
                     """)

        result = await self.session.execute(query, {"id_gleba": id_gleba})
        return result.mappings().first()


# =========================================================
# CLIMA
# =========================================================
class ClimaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def buscar_3_estacoes_mais_proximas(
            self,
            id_gleba: int
    ) -> List[Dict[str, Any]]:

        query = text("""
                     WITH gleba_info AS (
                         SELECT ST_Centroid(geometria) AS centroide
                         FROM agroprods.glebas
                         WHERE id_gleba = :id_gleba
                     ),
                          estacoes_proximas AS (
                              SELECT e.id, e.latitude, e.longitude
                              FROM agroprods.estacoes_inmet e, gleba_info g
                              ORDER BY ST_SetSRID(
                                               ST_MakePoint(e.longitude, e.latitude), 4326
                                       ) <-> g.centroide
                         LIMIT 3
                         )
                     SELECT ep.id,
                            ep.latitude,
                            ep.longitude,
                            COALESCE(sc.temp_c, 25.0) AS temp_c,
                            COALESCE(sc.chuva_mm, 12.0) AS chuva_mm
                     FROM estacoes_proximas ep
                              LEFT JOIN LATERAL (
                         SELECT temp_c, chuva_mm
                         FROM agroprods.series_climaticas_diarias
                         WHERE id_estacao = ep.id
                         ORDER BY data DESC, data_registro DESC
                             LIMIT 1
            ) sc ON TRUE
                     """)

        result = await self.session.execute(query, {"id_gleba": id_gleba})

        estacoes = []
        for row in result.mappings():
            estacoes.append({
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "temp_c": float(row["temp_c"]),
                "chuva_mm": float(row["chuva_mm"])
            })

        # fallback seguro
        if len(estacoes) < 3:
            return [
                {"latitude": -15.70, "longitude": -47.90, "temp_c": 25.0, "chuva_mm": 10.0},
                {"latitude": -15.90, "longitude": -48.00, "temp_c": 24.0, "chuva_mm": 12.0},
                {"latitude": -15.75, "longitude": -47.80, "temp_c": 26.0, "chuva_mm": 8.0}
            ]

        return estacoes


# =========================================================
# LEDGER
# =========================================================
class LedgerPersistenceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def obter_ultimo_hash_gleba(self, id_gleba: int) -> str:
        query = (
            select(ClassificacaoCultura.blockchain_hash)
            .where(ClassificacaoCultura.gleba_id == id_gleba)
            .order_by(
                desc(ClassificacaoCultura.data_classificacao),
                desc(ClassificacaoCultura.id)
            )
            .limit(1)
        )

        result = await self.session.execute(query)
        hash_encontrado = result.scalar_one_or_none()

        return hash_encontrado or "0" * 64

    async def salvar_bloco_ledger(
            self,
            dados_ia: dict,
            hash_atual: str,
            hash_anterior: str
    ):
        try:
            registro = ClassificacaoCultura(
                gleba_id=int(dados_ia["gleba_id"]),
                safra=dados_ia["safra"],
                cultura_predita=dados_ia.get("cultura"),
                cultura_real=dados_ia.get("cultura_real"),
                confianca_ia=float(dados_ia.get("confianca", 0.0)),
                produtividade_sacas_ha=float(dados_ia.get("produtividade", 0.0)),
                nitrogenio_grid=float(dados_ia.get("nitrogenio", 0.0)),
                prodes_conflito=bool(dados_ia.get("prodes", False)),
                bpa_status=bool(dados_ia.get("bpa", False)),
                srid_validado=4326,
                blockchain_hash=hash_atual,
                blockchain_anterior=hash_anterior
            )

            self.session.add(registro)
            await self.session.commit()
            await self.session.refresh(registro)

            return registro

        except Exception:
            await self.session.rollback()
            raise