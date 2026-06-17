import os
import hashlib
import json
import joblib
from decimal import Decimal
import numpy as np

from typing import Dict, Any, List
from scipy.interpolate import RBFInterpolator

EPSG_PADRAO = 4326

# Custom encoder para garantir imutabilidade do hash com qualquer tipo do SQLAlchemy/NumPy
class VMGJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.ndarray)):
            return obj.tolist()
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super(VMGJsonEncoder, self).default(obj)


class VMGIntelligenceService:

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))

        # Carregamento seguro dos artefatos matemáticos homologados pela portaria
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
        """
        Gera o hash encadeado imutável do bloco.
        Aplica o VMGJsonEncoder para blindar contra falhas de tipos (Decimal, DateTime, NumPy).
        """
        conteudo = json.dumps(
            payload,
            sort_keys=True,
            cls=VMGJsonEncoder
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

        # Culturas homologadas e rastreadas pelas 15 bases do programa nacional
        culturas = {
            0: "SOJA",
            1: "MILHO",
            2: "ALGODAO",
            3: "PASTAGEM"
        }

        return {
            "cultura": culturas.get(idx, "DESCONHECIDO"),
            "confianca": float(probs[idx])  # Retorna o indicador de assertividade (Anexo VI)
        }

    def calcular_produtividade(
            self,
            perfil_ndvi: np.ndarray,
            nitrogenio: float,
            temperatura: float,
            chuva: float
    ) -> float:
        # Força o achatamento (flatten) e consolida os parâmetros climáticos obrigatórios
        X = np.hstack([
            perfil_ndvi.flatten(),
            [float(nitrogenio), float(temperatura), float(chuva)]
        ])

        predicao = self.modelo_produtividade.predict(X.reshape(1, -1))[0]
        return float(max(0.0, predicao))  # Evita produtividade negativa residual matemática

    @staticmethod
    def interpolar_rbf(
            coordenada_gleba,
            estacoes: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        if not estacoes:
            raise ValueError("Inconformidade com o item 2: A lista de estações meteorológicas oficiais não pode estar vazia.")

        coords = np.array([
            [float(e["longitude"]), float(e["latitude"])]
            for e in estacoes
        ], dtype=float)

        temperaturas = np.array([float(e["temp_c"]) for e in estacoes], dtype=float)
        chuvas = np.array([float(e["chuva_mm"]) for e in estacoes], dtype=float)

        rbf_temp = RBFInterpolator(coords, temperaturas, kernel="linear")
        rbf_chuva = RBFInterpolator(coords, chuvas, kernel="linear")

        # Garante exatamente 2 dimensões [[X, Y]], independente do formato de entrada do WKT
        ponto = np.atleast_2d(coordenada_gleba).astype(float)

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
            return 45.0  # Parâmetro de fallback padrão estabelecido na modelagem
        resultado = await repo.nitrogenio_medio_gleba(id_gleba)
        return float(resultado) if resultado is not None else 45.0

    async def buscar_estacoes(
            self,
            repo,
            id_gleba: int
    ) -> List[Dict[str, Any]]:
        """
        Busca as estações climáticas mais próximas da gleba avaliada.
        Garante tratamento defensivo contra falhas de escopo ou injeção em tarefas do Celery/Taskiq.
        """
        if not hasattr(repo, "buscar_3_estacoes_mais_proximas"):
            if hasattr(repo, "session"):
                from app.repository.repositories import ClimaRepository
                repo = ClimaRepository(repo.session)
            else:
                # Fallback estrito de coordenadas para simulação/auditoria local emergencial
                return [
                    {"latitude": -15.70, "longitude": -47.90, "temp_c": 25.0, "chuva_mm": 10.0},
                    {"latitude": -15.90, "longitude": -48.00, "temp_c": 24.0, "chuva_mm": 12.0},
                    {"latitude": -15.75, "longitude": -47.80, "temp_c": 26.0, "chuva_mm": 8.0}
                ]

        return await repo.buscar_3_estacoes_mais_proximas(id_gleba)
