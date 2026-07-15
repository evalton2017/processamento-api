import hashlib
import json
import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List

import joblib
import numpy as np
from pystac_client import Client
from shapely.geometry import mapping
from shapely.wkt import loads
from scipy.interpolate import interp1d, RBFInterpolator
from sqlalchemy.dialects.postgresql import insert

logger = logging.getLogger(__name__)
EPSG_PADRAO = 4326
CONFIANCA_MINIMA_VMG = 0.80


class VMGIntelligenceService:

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        artefato_classificacao = joblib.load(
            os.path.join(base_dir, "modelos", "classificador_culturas.pkl")
        )
        if isinstance(artefato_classificacao, dict):
            self.modelo_classificacao = artefato_classificacao["modelo"]
            self.mapa_reverso_classes = artefato_classificacao.get("mapa_reverso_classes", {})
        else:
            self.modelo_classificacao = artefato_classificacao
            self.mapa_reverso_classes = {}
        self.modelo_produtividade = joblib.load(
            os.path.join(base_dir, "modelos", "produtividade.pkl")
        )

    @staticmethod
    def validar_epsg(srid: int) -> bool:
        return srid == EPSG_PADRAO

    @staticmethod
    def gerar_hash(payload: Dict[str, Any], hash_anterior: str) -> str:
        conteudo = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(f"{hash_anterior}{conteudo}".encode()).hexdigest()

    def _ajustar_escala_temporal_ndvi(self, dados_ndvi: np.ndarray, tamanho_alvo: int = 60) -> np.ndarray:
        tamanho_atual = len(dados_ndvi)
        if tamanho_atual == tamanho_alvo:
            return dados_ndvi

        x_atual = np.linspace(0, 1, tamanho_atual)
        x_alvo = np.linspace(0, 1, tamanho_alvo)

        interpolador = interp1d(x_atual, dados_ndvi, kind='linear', fill_value="extrapolate")
        return interpolador(x_alvo).astype(np.float32)

    def classificar_cultura(self, perfil_ndvi: Any) -> Dict[str, Any]:
        if isinstance(perfil_ndvi, list):
            valores_media = []
            for item in perfil_ndvi:
                if not isinstance(item, dict):
                    continue

                valor = item.get("ndvi_mean") or item.get("ndvi1_mean")

                if valor is not None:
                    try:
                        valores_media.append(float(valor))
                    except (ValueError, TypeError):
                        valores_media.append(0.0)
                else:
                    valores_media.append(0.0)

            perfil_ndvi = np.array(valores_media, dtype=np.float32)

        if (perfil_ndvi.size == 0 or
                np.isnan(perfil_ndvi).any() or
                np.all(perfil_ndvi == 0.0) or
                np.std(perfil_ndvi) < 1e-4):
            logger.error(f"[MÓDULO IA] Falha crítica: Perfil NDVI sem variabilidade temporal ou inválido.")
            return {
                "cultura": "DESCONHECIDO",
                "confianca": 0.0,
                "status": "SEM_DADOS"
            }

        ndvi_plano = perfil_ndvi.ravel()
        if len(ndvi_plano) != 60:
            ndvi_plano = self._ajustar_escala_temporal_ndvi(ndvi_plano, 60)

        X = np.asarray(ndvi_plano, dtype=np.float32).reshape(1, -1)

        probs_matriz = self.modelo_classificacao.predict_proba(X)
        probs = np.atleast_1d(probs_matriz[0])

        idx_interno_xgb = int(np.argmax(probs))
        confianca = float(probs[idx_interno_xgb])

        retorno_pkl = None
        if hasattr(self, "mapa_reverso_classes") and self.mapa_reverso_classes:
            retorno_pkl = self.mapa_reverso_classes.get(idx_interno_xgb)

        if hasattr(self.modelo_classificacao, "classes_") and not retorno_pkl:
            try:
                retorno_pkl = self.modelo_classificacao.classes_[idx_interno_xgb]
            except IndexError:
                retorno_pkl = None

        if retorno_pkl is not None:
            if isinstance(retorno_pkl, (int, np.integer)) or str(retorno_pkl).isdigit():
                classes_recalibradas = {
                    0: "ALGODAO", 1: "ARROZ", 2: "CAFE",
                    3: "CANA", 4: "MILHO", 5: "SOJA"
                }
                cultura_identificada = classes_recalibradas.get(int(retorno_pkl), "DESCONHECIDO")
            else:
                cultura_identificada = str(retorno_pkl)
        else:
            cultura_identificada = "DESCONHECIDO"

        cultura_identificada = cultura_identificada.upper().strip()
        status = "HOMOLOGADO" if confianca >= CONFIANCA_MINIMA_VMG else "REVISAO_MANUAL"

        return {
            "cultura": cultura_identificada,
            "confianca": confianca,
            "status": status
        }

    def calcular_produtividade(self, perfil_ndvi: Any, nitrogenio: float, temperatura: float, chuva: float) -> float:
        if isinstance(perfil_ndvi, list):
            valores_media = []
            for item in perfil_ndvi:
                if not isinstance(item, dict):
                    continue
                valor = item.get("ndvi_mean") if item.get("ndvi_mean") is not None else item.get("ndvi_mean", 0.0)
                valores_media.append(float(valor or 0.0))
            perfil_ndvi = np.array(valores_media, dtype=np.float32)

        if perfil_ndvi is None or perfil_ndvi.size == 0 or np.all(perfil_ndvi == 0.0):
            logger.warning("[PRODUTIVIDADE] Abortando cálculo matemático: série temporal de NDVI vazia ou inválida.")
            return 0.0
        ndvi_plano = perfil_ndvi.flatten()

        if len(ndvi_plano) != 60:
            ndvi_plano = self._ajustar_escala_temporal_ndvi(ndvi_plano, 60)

        X = np.hstack([
            ndvi_plano,
            [float(nitrogenio), float(temperatura), float(chuva)]
        ]).reshape(1, -1)

        predicao = self.modelo_produtividade.predict(X)[0]
        return float(max(0.0, predicao))

    @staticmethod
    def interpolar_rbf(coordenada_gleba, estacoes: List[Dict[str, Any]]) -> Dict[str, float]:
        if not estacoes or len(estacoes) < 3:
            logger.error(f"Inconformidade Portaria VMG: Mínimo de 3 estações operantes exigido.")
            raise ValueError(
                "Erro de Infraestrutura: Triangulação climática exige pelo menos 3 estações meteorológicas operantes.")

        coords = np.array([[float(e["longitude"]), float(e["latitude"])] for e in estacoes], dtype=float)
        temperaturas = np.array([float(e["temp_c"]) for e in estacoes], dtype=float)
        chuvas = np.array([float(e["chuva_mm"]) for e in estacoes], dtype=float)

        rbf_temp = RBFInterpolator(coords, temperaturas, kernel="linear")
        rbf_chuva = RBFInterpolator(coords, chuvas, kernel="linear")

        ponto = np.atleast_2d(coordenada_gleba).astype(float)
        temperatura_final = float(rbf_temp(ponto)[0])
        chuva_final = float(rbf_chuva(ponto)[0])

        return {
            "temperatura": temperatura_final,
            "chuva": chuva_final
        }

    async def validar_prodes(self, repo, id_gleba: int) -> bool:
        if not hasattr(repo, "existe_intersecao"):
            return False
        return await repo.existe_intersecao(id_gleba)

    async def validar_bpa(self, repo, id_produtor: int) -> bool:
        if not hasattr(repo, "possui_certificado_valido"):
            return False
        return await repo.possui_certificado_valido(id_produtor)

    async def obter_nitrogenio_medio(self, repo, id_gleba: int) -> float:
        if not hasattr(repo, "nitrogenio_medio_gleba"):
            return 45.0
        resultado = await repo.nitrogenio_medio_gleba(id_gleba)
        return float(resultado) if resultado is not None else 45.0

    async def buscar_estacoes(self, repo, id_gleba: int) -> List[Dict[str, Any]]:
        if not hasattr(repo, "buscar_3_estacoes_mais_proximas"):
            if hasattr(repo, "session"):
                from app.repository.repositories import ClimaRepository
                repo = ClimaRepository(repo.session)
            else:
                return [
                    {"latitude": -15.70, "longitude": -47.90, "temp_c": 25.0, "chuva_mm": 10.0},
                    {"latitude": -15.90, "longitude": -48.00, "temp_c": 24.0, "chuva_mm": 12.0},
                    {"latitude": -15.75, "longitude": -47.80, "temp_c": 26.0, "chuva_mm": 8.0}
                ]
        return await repo.buscar_3_estacoes_mais_proximas(id_gleba)

    async def sincronizar_rasters_gleba(
            self, solo_repo, geometria_wkt: str, id_gleba: int, data_inicio, data_fim
    ):
        """Sincroniza os metadados salvando os links corretos de red e nir no banco de dados."""
        async for imagem in self.buscar_imagens_sentinel_stream(
                geometria_wkt=geometria_wkt, data_inicio=data_inicio, data_fim=data_fim
        ):
            await solo_repo.salvar_metadado_raster(
                id_gleba=id_gleba,
                data_captura=imagem["data"],
                raster_url=imagem["raster_url"],
                hash_sha256=imagem["hash_sha256"],
                geom=geometria_wkt,
                cloud_cover=imagem["cloud_cover"]
            )

    async def buscar_imagens_sentinel_stream(
            self, geometria_wkt: str, data_inicio: datetime, data_fim: datetime, max_nuvem: float = 30.0
    ):
        """
        Busca imagens do Sentinel-2 rodando a API síncrona do pystac no executor thread-pool
        para evitar travamentos eternos de I/O de rede no Worker Taskiq.
        """
        loop = asyncio.get_running_loop()
        geometria = loads(geometria_wkt)

        intervalo_tempo = f"{data_inicio.strftime('%Y-%m-%d')}/{data_fim.strftime('%Y-%m-%d')}"

        def executar_busca_stac():
            # Abre o cliente com timeout interno
            catalog = Client.open("https://earth-search.aws.element84.com/v1")
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                intersects=mapping(geometria),
                datetime=intervalo_tempo,
                query={"eo:cloud_cover": {"lte": max_nuvem}},
                max_items=100  # Evita trazer milhares de itens por acidente e estourar a memória/timeout
            )
            # Retorna uma lista de itens processados síncronos
            return list(search.items())

        try:
            # Roda a busca síncrona pesada sem travar o Event Loop do Asyncio
            itens = await asyncio.wait_for(
                loop.run_in_executor(None, executar_busca_stac),
                timeout=45.0  # Timeout de segurança de 45 segundos para a API STAC
            )
        except asyncio.TimeoutError:
            logger.error("Timeout de 45s ao acessar a API STAC Element84. Pulando busca remota.")
            itens = []
        except Exception as e:
            logger.error(f"Erro ao conectar ou buscar imagens na API do STAC: {str(e)}")
            itens = []

        for item in itens:
            try:
                if "nir" not in item.assets or "red" not in item.assets:
                    continue

                # Evita links expirados preferindo o href do gsd
                nir_url = item.assets["nir"].href
                red_url = item.assets["red"].href

                hash_sha256 = hashlib.sha256(red_url.encode("utf-8")).hexdigest()
                data_captura = item.datetime.date() if item.datetime else data_inicio.date()

                yield {
                    "data": data_captura,
                    "nir_url": nir_url,
                    "raster_url": f"{red_url}|{nir_url}",
                    "hash_sha256": hash_sha256,
                    "cloud_cover": float(item.properties.get("eo:cloud_cover", 0.0)),
                }
            except Exception:
                logger.exception("Erro ao processar item do catálogo STAC %s", item.id)
                continue

    async def salvar_dados_para_treinamento(
            self,
            db_session,  # Recomenda-se passar a sessão ativa explicitamente
            gleba_id: int,
            safra: str,
            ndvi: list,
            cultura_real: str
    ) -> None:
        """
        Salva os vetores estruturados para retreino.
        Usa o construtor Postgres nativo de UPSERT para evitar quebras do driver Asyncpg.
        """
        from sqlalchemy import Table, MetaData, Column, Integer, String
        from sqlalchemy.dialects.postgresql import JSONB

        # Define a tabela dinamicamente ou use sua definição declarativa se disponível
        metadata = MetaData()
        tabela_treinamento = Table(
            "treinamento_culturas",
            metadata,
            Column("gleba_id", Integer, primary_key=True),
            Column("safra", String, primary_key=True),
            Column("ndvi", JSONB),
            Column("cultura_real", String),
            schema="agroprods"
        )

        query_upsert = insert(tabela_treinamento).values(
            gleba_id=gleba_id,
            safra=safra,
            ndvi=ndvi,
            cultura_real=cultura_real.upper()
        )

        stmt_final = query_upsert.on_conflict_do_update(
            index_elements=["gleba_id", "safra"],
            set_={
                "ndvi": query_upsert.excluded.ndvi,
                "cultura_real": query_upsert.excluded.cultura_real
            }
        )

        await db_session.execute(stmt_final)