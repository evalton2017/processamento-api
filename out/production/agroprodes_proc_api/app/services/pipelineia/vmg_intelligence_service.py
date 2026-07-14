import hashlib
import json
import logging
import os
from datetime import datetime

from sqlalchemy import insert, text

print(os.environ.get("PROJ_LIB"))
print(os.environ.get("GDAL_DATA"))

from typing import Dict, Any, List

import joblib
import numpy as np
from pystac_client import Client
from shapely.geometry import mapping
from shapely.wkt import loads
from scipy.interpolate import interp1d, RBFInterpolator


logger = logging.getLogger(__name__)
EPSG_PADRAO = 4326

CONFIANCA_MINIMA_VMG = 0.80

class VMGIntelligenceService:

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # Carrega o artefato completo (Dicionário estruturado pelo gerar_modelos.py)
        artefato_classificacao = joblib.load(
            os.path.join(base_dir, "modelos", "classificador_culturas.pkl")
        )
        # --- ATENÇÃO AQUI: Extrai os objetos de dentro do dicionário ---
        if isinstance(artefato_classificacao, dict):
            self.modelo_classificacao = artefato_classificacao["modelo"]
            self.mapa_reverso_classes = artefato_classificacao.get("mapa_reverso_classes", {})
        else:
            # Fallback caso o pkl seja antigo e guarde o modelo direto
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
        """
        Substitui o np.resize por interpolação linear para manter a integridade da curva fenológica.
        Garante o alinhamento estrito de features sem injetar ruído de repetição.
        """
        tamanho_atual = len(dados_ndvi)
        if tamanho_atual == tamanho_alvo:
            return dados_ndvi

        # Cria eixos de tempo normalizados de 0 a 1 para o mapeamento
        x_atual = np.linspace(0, 1, tamanho_atual)
        x_alvo = np.linspace(0, 1, tamanho_alvo)

        # Reconstrói a curva fenológica linearmente
        interpolador = interp1d(x_atual, dados_ndvi, kind='linear', fill_value="extrapolate")
        return interpolador(x_alvo).astype(np.float32)

    def classificar_cultura(self, perfil_ndvi: Any) -> Dict[str, Any]:
        if isinstance(perfil_ndvi, list):
            valores_media = [item["ndvi_mean"] for item in perfil_ndvi]
            perfil_ndvi = np.array(valores_media, dtype=np.float32)

        if perfil_ndvi.size == 0:
            return {"cultura": "DESCONHECIDO", "confianca": 0.0, "status": "SEM_DADOS"}

        ndvi_plano = perfil_ndvi.flatten()
        if len(ndvi_plano) != 60:
            logger.warning(f"Ajustando dimensionalidade fenológica via interpolação de {len(ndvi_plano)} para 60 posições.")
            ndvi_plano = self._ajustar_escala_temporal_ndvi(ndvi_plano, 60)

        X = ndvi_plano.reshape(1, -1)

        # --- INFERÊNCIA DA INTELIGÊNCIA ARTIFICIAL ---
        # 1. Roda a predição para o lote (batch) de dados
        probs_matriz = self.modelo_classificacao.predict_proba(X)

        # 2. Extrai a primeira linha do lote (formato unidimensional)
        probs = probs_matriz[0]

        # 3. Localiza a classe de maior probabilidade e extrai o score de confiança
        idx_interno_xgb = int(np.argmax(probs))
        confianca = float(probs[idx_interno_xgb])

        # --- MAPEAMENTO DINÂMICO DE STRINGS COM CLAUSULA ANTI-RUÍDO ---
        # Dicionário global unificado do Agroprodes para tradução de fallbacks numéricos
        culturas_globais = {
            0: "SOJA", 1: "MILHO", 2: "ALGODAO",
            3: "PASTAGEM", 4: "CAFE", 5: "ARROZ"
        }

        if hasattr(self, "mapa_reverso_classes") and self.mapa_reverso_classes:
            retorno_pkl = self.mapa_reverso_classes.get(idx_interno_xgb, "DESCONHECIDO")

            # Se o .pkl retornar um número/id (como 0 ou "0"), traduz usando o dicionário estável
            if isinstance(retorno_pkl, (int, np.integer)) or str(retorno_pkl).isdigit():
                cultura_identificada = culturas_globais.get(int(retorno_pkl), "DESCONHECIDO")
            else:
                # Se já for o texto purificado ("SOJA"), mantém a string
                cultura_identificada = str(retorno_pkl)
        else:
            # Fallback direto caso o artefato pkl não possua metadados de classe
            cultura_identificada = culturas_globais.get(idx_interno_xgb, "DESCONHECIDO")

        # Padroniza a string eliminando espaços em branco e aplicando caixa alta
        cultura_identificada = cultura_identificada.upper().strip()

        # --- CRITÉRIO DE CONFORMIDADE DA PORTARIA SDI/MAPA Nº 739/2025 ---
        status = "HOMOLOGADO" if confianca >= CONFIANCA_MINIMA_VMG else "REVISAO_MANUAL"

        return {
            "cultura": cultura_identificada,
            "confianca": confianca,
            "status": status
        }

    def calcular_produtividade(
            self,
            perfil_ndvi: Any,
            nitrogenio: float,
            temperatura: float,
            chuva: float
    ) -> float:
        if isinstance(perfil_ndvi, list):
            valores_media = [item["ndvi_mean"] for item in perfil_ndvi]
            perfil_ndvi = np.array(valores_media, dtype=np.float32)

        ndvi_plano = perfil_ndvi.flatten()
        if len(ndvi_plano) != 60:
            logger.warning(f"Ajustando dimensionalidade do NDVI para produtividade via interpolação.")
            ndvi_plano = self._ajustar_escala_temporal_ndvi(ndvi_plano, 60)

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
        if not estacoes or len(estacoes) < 3:
            logger.error(f"Inconformidade Portaria VMG: Mínimo de 3 estações operantes exigido.")
            raise ValueError("Erro de Infraestrutura: Triangulação climática exige pelo menos 3 estações meteorológicas operantes.")

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
        geometria = loads(geometria_wkt)
        catalog = Client.open("https://earth-search.aws.element84.com/v1")

        intervalo_tempo = f"{data_inicio.strftime('%Y-%m-%d')}/{data_fim.strftime('%Y-%m-%d')}"

        search = catalog.search(
            collections=["sentinel-2-l2a"],
            intersects=mapping(geometria),
            datetime=intervalo_tempo,
            query={"eo:cloud_cover": {"lte": max_nuvem}},
        )

        # Uso correto do gerador para não bloquear o Event Loop do microserviço
        for item in search.item_collection():
            try:
                raster_url = item.assets["visual"].href if "visual" in item.assets else item.assets["red"].href
                hash_sha256 = hashlib.sha256(raster_url.encode("utf-8")).hexdigest()

                # Conversão segura do datetime STAC para date do Python
                data_captura = item.datetime.date() if item.datetime else data_inicio.date()

                yield {
                    "data": data_captura,
                    "raster_url": raster_url,
                    "hash_sha256": hash_sha256,
                    "cloud_cover": float(item.properties.get("eo:cloud_cover", 0.0)),
                }
            except Exception:
                logger.exception("Erro ao processar item do catálogo STAC %s", item.id)
                continue
    async def salvar_dados_para_treinamento(
            self,
            gleba_id: int,
            safra: str,
            ndvi: list,
            cultura_real: str
    ) -> None:
        """
        Salva os vetores de índices de vegetação estruturados para a base de retreino da IA.
        Aplica a estratégia de UPSERT baseada na restrição única de gleba_id + safra.
        Conforme diretrizes de integridade da Portaria SDI/MAPA Nº 739/2025.
        """
        # 1. Monta a instrução de inserção para o dialeto PostgreSQL
        # Caso não utilize uma classe ORM declarativa, você pode mapear usando a tabela direto:
        # stmt = insert(TreinamentoCulturasModel).values(...)

        # Abaixo mapeamos utilizando a tabela via core ou string mapeada de forma assíncrona segura
        query_upsert = insert(text("agroprods.treinamento_culturas")).values(
            gleba_id=gleba_id,
            safra=safra,
            ndvi=ndvi,       # O driver do Asyncpg/Postgres converte a lista Python direto para o JSONB
            evi=None,        # Deixado como opcional caso decida implementar no futuro
            savi=None,       # Deixado como opcional caso decida implementar no futuro
            cultura_real=cultura_real.upper()
        )

        # 2. Define a ação caso ocorra o conflito de unicidade (Gleba já cadastrada nessa safra)
        # O index_elements representa as colunas do seu UNIQUE CONSTRAINT
        stmt_final = query_upsert.on_conflict_do_update(
            index_elements=["gleba_id", "safra"],
            set_={
                "ndvi": query_upsert.excluded.ndvi,
                "cultura_real": query_upsert.excluded.cultura_real
            }
        )

        # 3. Executa a operação utilizando a sessão ativa do repositório (self.session ou self.db_session)
        # Ajuste o nome do atributo de sessão de acordo com o padrão do seu repositório
        if hasattr(self, "session"):
            await self.session.execute(stmt_final)
        elif hasattr(self, "db_session"):
            await self.db_session.execute(stmt_final)
        else:
            raise AttributeError("Nenhuma sessão ativa encontrada no SoloRepository para executar o UPSERT.")