from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from narwhals import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, desc

from app.models.models_ledger import AtestadosVmgLedger


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
                            volume_declarado_comercializar,data_estimada_colheita,
                            ST_AsText(geometria) as geometria
                     FROM agroprods.glebas
                     WHERE id_gleba = :id_gleba
                     """)

        result = await self.session.execute(query, {"id_gleba": id_gleba})
        return result.mappings().first()

    async def buscar_rasters(self, id_gleba: int, data_inicio, data_fim):
        result = await self.session.execute(
            text(
                """
                SELECT
                    id_raster,
                    id_gleba,
                    data_captura,
                    ndvi_mean,
                    ndvi_std,
                    cloud_cover, -- Nome correto conforme sua tabela
                    raster_url,
                    ST_AsText(geom) as geometria_wkt,
                    hash_sha256
                FROM agroprods.metadados_raster
                WHERE id_gleba = :id_gleba
                  AND data_captura BETWEEN :data_inicio AND :data_fim
                ORDER BY data_captura ASC
                """
            ),
            {
                "id_gleba": id_gleba,
                "data_inicio": data_inicio,
                "data_fim": data_fim
            }
        )
        return result.mappings().all()

    async def atualizar_estatisticas_ndvi(self, id_raster: int, ndvi_mean: float, ndvi_std: float):
        """
        Atualiza as colunas de estatísticas de NDVI calculadas via COG Streaming.
        """
        await self.session.execute(
            text(
                """
                UPDATE agroprods.metadados_raster
                SET ndvi_mean = :ndvi_mean,
                    ndvi_std = :ndvi_std
                WHERE id_raster = :id_raster
                """
            ),
            {
                "id_raster": id_raster,
                "ndvi_mean": ndvi_mean,
                "ndvi_std": ndvi_std
            }
        )

    async def salvar_metadado_raster(
            self,
            id_gleba: int,
            data_captura,
            raster_url: str,
            hash_sha256: str,
            geom: str,
            cloud_cover: float,
            ndvi_mean: float = None,
            ndvi_std: float = None,
    ):
        await self.session.execute(
            text(
                """
                INSERT INTO agroprods.metadados_raster
                (
                    id_gleba,
                    data_captura,
                    raster_url,
                    hash_sha256,
                    geom,
                    cloud_cover,
                    ndvi_mean,
                    ndvi_std
                )
                VALUES
                    (
                        :id_gleba,
                        :data_captura,
                        :raster_url,
                        :hash_sha256,
                        ST_GeomFromText(:geom, 4326),
                        :cloud_cover,
                        :ndvi_mean,
                        :ndvi_std
                    )
                    ON CONFLICT (id_gleba, data_captura)
            DO NOTHING
                """
            ),
            {
                "id_gleba": id_gleba,
                "data_captura": data_captura,
                "raster_url": raster_url,
                "hash_sha256": hash_sha256,
                "geom": geom,
                "cloud_cover": cloud_cover,
                "ndvi_mean": ndvi_mean,
                "ndvi_std": ndvi_std,
            },
        )
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
        """
        Busca o hash mais recente gerado para uma determinada gleba na tabela mestre do ledger.
        Retorna uma string de 64 zeros caso seja a primeira validação da gleba (Gênese).
        """
        query = (
            select(AtestadosVmgLedger.hash_relatorio)
            .where(AtestadosVmgLedger.id_gleba == id_gleba)
            .order_by(
                desc(AtestadosVmgLedger.data_emissao),
                desc(AtestadosVmgLedger.id_atestado)  # PK corrigida aqui
            )
            .limit(1)
        )

        result = await self.session.execute(query)
        hash_encontrado = result.scalar_one_or_none()

        return hash_encontrado or "0" * 64

    async def salvar_bloco_ledger(
            self,
            dados_ia: Dict[str, Any],
            hash_atual: str
    ) -> AtestadosVmgLedger:
        """
        Instancia e adiciona o registro mestre de auditoria na sessão.
        Nota: O commit NÃO é realizado aqui dentro para garantir a atomicidade
        do pipeline (padrão Unit of Work).
        """
        # 1. Mapeamento estrito do status baseado na regra do banco (CHECK CONSTRAINT)
        # O banco exige: 'APROVADO', 'REPROVADO' ou 'PENDENTE'
        bloqueado = bool(dados_ia.get("bloqueio_socioambiental", False))
        status_validacao = "REPROVADO" if bloqueado else "APROVADO"

        # 2. Resolução do tipo de contrato conforme regras do banco (CHECK CONSTRAINT)
        # O banco exige: 'Plano Safra', 'PSR' ou 'Proagro'
        # Buscamos do payload ou aplicamos um padrão válido exigido pela portaria
        tipo_contrato = dados_ia.get("tipo_contrato", "Plano Safra")
        if tipo_contrato not in ["Plano Safra", "PSR", "Proagro"]:
            tipo_contrato = "Plano Safra"

        import builtins
        # 1. Força a importação do pacote numérico nativo do Python localmente
        from decimal import Decimal as PythonDecimal

        produtividade_float = dados_ia.get("produtividade", 0.0)
        produtividade_arredondada = builtins.round(produtividade_float, 2)

        # 2. Utiliza o alias seguro para converter para o Decimal correto do banco de dados
        produtividade_decimal = PythonDecimal(str(produtividade_arredondada))

        # 4. Instanciação alinhada com as colunas reais do banco físico
        registro_ledger = AtestadosVmgLedger(
            id_gleba=int(dados_ia["gleba_id"]),
            tipo_contrato=tipo_contrato,
            status_validacao=status_validacao,
            estimativa_produtividade_sacas=produtividade_decimal,
            data_emissao=datetime.utcnow(),
            hash_relatorio=str(hash_atual)
        )

        # Adiciona à sessão unitária do pipeline principal
        self.session.add(registro_ledger)

        return registro_ledger

