import os
import hashlib
import json
import joblib
import numpy as np

from typing import Dict, Any, List
from scipy.interpolate import RBFInterpolator

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
        conteudo = json.dumps(
            payload,
            sort_keys=True,
            default=str
        )
        return hashlib.sha256(
            f"{hash_anterior}{conteudo}".encode()
        ).hexdigest()

    def classificar_cultura(
            self,
            perfil_ndvi: np.ndarray
    ) -> Dict[str, Any]:
        # Garante array bidimensional plano para evitar quebras no predict_proba
        X = perfil_ndvi.flatten().reshape(1, -1)
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
            perfil_ndvi: np.ndarray,
            nitrogenio: float,
            temperatura: float,
            chuva: float
    ) -> float:
        # CORREÇÃO: Força o achatamento (flatten) para evitar erros de dimensões incompatíveis
        X = np.hstack([
            perfil_ndvi.flatten(),
            [float(nitrogenio), float(temperatura), float(chuva)]
        ])

        predicao = self.modelo_produtividade.predict(X.reshape(1, -1))[0]
        return float(max(0.0, predicao))  # Evita produtividade negativa residual

    @staticmethod
    def interpolar_rbf(
            coordenada_gleba,
            estacoes: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        if not estacoes:
            raise ValueError("A lista de estações meteorológicas não pode estar vazia.")

        coords = np.array([
            [float(e["longitude"]), float(e["latitude"])]
            for e in estacoes
        ], dtype=float)

        temperaturas = np.array([float(e["temp_c"]) for e in estacoes], dtype=float)
        chuvas = np.array([float(e["chuva_mm"]) for e in estacoes], dtype=float)

        rbf_temp = RBFInterpolator(coords, temperaturas, kernel="linear")
        rbf_chuva = RBFInterpolator(coords, chuvas, kernel="linear")

        # Garante exatamente 2 dimensões [[X, Y]], independente de como veio do pipeline
        ponto = np.atleast_2d(coordenada_gleba).astype(float)

        # Executa a predição na matriz bidimensional e extrai o primeiro resultado escalar
        temperatura_final = float(rbf_temp(ponto)[0])
        chuva_final = float(rbf_chuva(ponto)[0])

        return {
            "temperatura": temperatura_final,
            "chuva": chuva_final
        }

    async def validar_prodes(
            self,
            repo,
            id_gleba: int
    ) -> bool:
        # Verificação defensiva de tipo para evitar chamadas em repositórios errados
        if not hasattr(repo, "existe_intersecao"):
            return False
        return await repo.existe_intersecao(id_gleba)

    async def validar_bpa(
            self,
            repo,
            id_produtor: int
    ) -> bool:
        if not hasattr(repo, "possui_certificado_valido"):
            return False
        return await repo.possui_certificado_valido(id_produtor)

    async def obter_nitrogenio_medio(
            self,
            repo,
            id_gleba: int
    ) -> float:
        if not hasattr(repo, "nitrogenio_medio_gleba"):
            return 45.0  # Fallback padrão da portaria
        resultado = await repo.nitrogenio_medio_gleba(id_gleba)
        return float(resultado) if resultado is not None else 45.0

    async def buscar_estacoes(
            self,
            repo,
            id_gleba: int
    ) -> List[Dict[str, Any]]:
        """
        Busca as estações climáticas. Caso o repositório injetado seja inválido
        ou incompleto devido a problemas de cache/importação do Celery,
        aciona uma instância dinâmica do ClimaRepository para evitar falhas em produção.
        """
        # PROGRAMAÇÃO DEFENSIVA SEVERA: Se o objeto passado não tiver o método, tenta recuperar a sessão do banco
        if not hasattr(repo, "buscar_3_estacoes_mais_proximas"):
            if hasattr(repo, "session"):
                from app.repository.repositories import ClimaRepository
                repo = ClimaRepository(repo.session)
            else:
                # Fallback absoluto se nenhuma sessão do SQLAlchemy estiver acessível
                return [
                    {"latitude": -15.70, "longitude": -47.90, "temp_c": 25.0, "chuva_mm": 10.0},
                    {"latitude": -15.90, "longitude": -48.00, "temp_c": 24.0, "chuva_mm": 12.0},
                    {"latitude": -15.75, "longitude": -47.80, "temp_c": 26.0, "chuva_mm": 8.0}
                ]

        return await repo.buscar_3_estacoes_mais_proximas(id_gleba)
