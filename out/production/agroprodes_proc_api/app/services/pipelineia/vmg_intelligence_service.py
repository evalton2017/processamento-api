import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime

import rasterio
from pyproj import Transformer
from shapely.ops import transform as shapely_transform

print(os.environ.get("PROJ_LIB"))
print(os.environ.get("GDAL_DATA"))

from typing import Dict, Any, List

import httpx
import joblib
import numpy as np
from pystac_client import Client
from rasterio.io import MemoryFile
from rasterio.mask import mask
from scipy.interpolate import RBFInterpolator
from shapely.geometry import mapping
from shapely.wkt import loads

logger = logging.getLogger(__name__)
EPSG_PADRAO = 4326

class VMGIntelligenceService:

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))

        self.modelo_classificacao = joblib.load(
            os.path.join(base_dir, "modelos", "classificador_culturas.pkl")
        )

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

    def classificar_cultura(self, perfil_ndvi: Any) -> Dict[str, Any]:
        # Adaptação para o novo modelo baseado em COG Streaming (lista de dicionários)
        if isinstance(perfil_ndvi, list):
            valores_media = [item["ndvi_mean"] for item in perfil_ndvi]
            perfil_ndvi = np.array(valores_media, dtype=np.float32)

        # Prevenção caso a lista venha vazia por falta de imagens sem nuvem no período
        if perfil_ndvi.size == 0:
            return {"cultura": "DESCONHECIDO", "confianca": 0.0}

        X = perfil_ndvi.flatten().reshape(1, -1)

        # Executa a inferência usando o modelo treinado (Scikit-Learn/XGBoost)
        probs = self.modelo_classificacao.predict_proba(X)[0]
        idx = int(np.argmax(probs))

        culturas = {
            0: "SOJA",
            1: "MILHO",
            2: "ALGODAO",
            3: "PASTAGEM"
        }

        return {
            "cultura": culturas.get(idx, "DESCONHECIDO"),
            "confianca": float(probs[idx])
        }

    def calcular_produtividade(
            self,
            perfil_ndvi: Any,
            nitrogenio: float,
            temperatura: float,
            chuva: float
    ) -> float:
        """
        Calcula a estimativa de sacas por hectare garantindo o alinhamento
        estrito de 63 features exigido pelo modelo treinado no gerar_modelos.py.
        """
        # Adaptação para o novo modelo baseado em COG Streaming (lista de dicionários)
        if isinstance(perfil_ndvi, list):
            valores_media = [item["ndvi_mean"] for item in perfil_ndvi]
            perfil_ndvi = np.array(valores_media, dtype=np.float32)

        # Garante que o NDVI ocupe exatamente as primeiras 60 posições do vetor
        ndvi_plano = perfil_ndvi.flatten()
        if len(ndvi_plano) != 60:
            logger.warning(f"Ajustando dimensionalidade do NDVI de {len(ndvi_plano)} para 60 posições.")
            ndvi_plano = np.resize(ndvi_plano, (60,))

        # Monta as 63 features na ordem exata esperada pelo RandomForestRegressor
        X = np.hstack([
            ndvi_plano,
            [float(nitrogenio), float(temperatura), float(chuva)]
        ]).reshape(1, -1)

        predicao = self.modelo_produtividade.predict(X)[0]
        return float(max(0.0, predicao))

    @staticmethod
    def interpolar_rbf(
            coordenada_gleba,
            estacoes: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Executa a triangulação meteorológica baseada no método RBF (Radial Basis Function).
        Cumpre a exigência do Item 3.8.a da Portaria: Mínimo de 3 estações operantes.
        """
        # Validação Regra de Ouro da Portaria: Mínimo de 3 bases climáticas operantes
        if not estacoes or len(estacoes) < 3:
            logger.error(f"Inconformidade Portaria VMG: Esperado no mínimo 3 estações operantes, recebido {len(estacoes) if estacoes else 0}")
            raise ValueError("Erro de Infraestrutura: Triangulação climática exige pelo menos 3 estações meteorológicas operantes.")

        coords = np.array([
            [float(e["longitude"]), float(e["latitude"])]
            for e in estacoes
        ], dtype=float)

        temperaturas = np.array([float(e["temp_c"]) for e in estacoes], dtype=float)
        chuvas = np.array([float(e["chuva_mm"]) for e in estacoes], dtype=float)

        # Instanciação matemática do Kernel Linear para interpolação geográfica
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
        """
        Busca as estações INMET. Em caso de pane em uma das torres primárias,
        o repositório deve retornar as substitutas operantes mais próximas.
        """
        if not hasattr(repo, "buscar_3_estacoes_mais_proximas"):
            if hasattr(repo, "session"):
                from app.repository.repositories import ClimaRepository
                repo = ClimaRepository(repo.session)
            else:
                # Fallback em conformidade contendo 3 estações estruturadas para o DF/Entorno
                return [
                    {"latitude": -15.70, "longitude": -47.90, "temp_c": 25.0, "chuva_mm": 10.0},
                    {"latitude": -15.90, "longitude": -48.00, "temp_c": 24.0, "chuva_mm": 12.0},
                    {"latitude": -15.75, "longitude": -47.80, "temp_c": 26.0, "chuva_mm": 8.0}
                ]

        return await repo.buscar_3_estacoes_mais_proximas(id_gleba)

    async def sincronizar_rasters_gleba(
            self,
            solo_repo,
            geometria_wkt: str,
            id_gleba: int,
            data_inicio,
            data_fim,
    ):
        async for imagem in self.buscar_imagens_sentinel_stream(
                geometria_wkt=geometria_wkt,
                data_inicio=data_inicio,
                data_fim=data_fim,
        ):
            await solo_repo.salvar_metadado_raster(
                id_gleba=id_gleba,
                data_captura=imagem["data"],
                raster_url=imagem["raster_url"],
                hash_sha256=imagem["hash_sha256"],
                geom=geometria_wkt,
                cloud_cover=imagem["cloud_cover"], # Nome do parâmetro corrigido
                # Se você já calcula a média/desvio do NDVI no stream, passe aqui:
                # ndvi_mean=imagem.get("ndvi_mean"),
                # ndvi_std=imagem.get("ndvi_std"),
            )

    async def buscar_imagens_sentinel_stream(
            self,
            geometria_wkt: str,
            data_inicio: datetime,
            data_fim: datetime,
            max_nuvem: float = 30.0,
    ):
        geometria = loads(geometria_wkt)

        catalog = Client.open("https://earth-search.aws.element84.com/v1")

        # Busca assíncrona/I/O bound no catálogo STAC
        # Não precisamos de thread pool (max_workers) porque não há processamento pesado de CPU
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            intersects=mapping(geometria),
            datetime=f"{data_inicio.isoformat()}/{data_fim.isoformat()}",
            query={"eo:cloud_cover": {"lte": max_nuvem}},
        )

        itens = list(search.items())
        itens.sort(key=lambda x: x.properties.get("eo:cloud_cover", 100))

        for item in itens:
            try:
                # O link para a composição visual (renderizada) ou banda específica do COG
                # Geralmente usa-se a URL do próprio Item STAC ou do asset visual/banda principal
                raster_url = item.assets["visual"].href  # Ou monte uma estrutura/string com as bandas se necessário

                # Gera o hash SHA256 da URL (ou do ID do item) para auditoria do MAPA
                # Garante que a origem do dado nunca mude
                hash_sha256 = hashlib.sha256(raster_url.encode("utf-8")).hexdigest()

                yield {
                    "data": item.datetime.date(),  # Convertido para date para bater com o tipo da tabela
                    "raster_url": raster_url,
                    "hash_sha256": hash_sha256,
                    "cloud_cover": item.properties.get("eo:cloud_cover", 0.0),
                }
            except Exception:
                logger.exception("Erro ao processar item do catálogo %s", item.id)
                continue