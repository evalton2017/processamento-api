import asyncio
import numpy as np
import pandas as pd
from typing import List, Dict, Any

from app.services.vmg_intelligence_service import VMGIntelligenceService

# ==============================================================================
# FUNÇÕES PURAS ISOLADAS (Protegidas contra corrupção de cache do Taskiq)
# ==============================================================================
def rotina_numérica_ndvi() -> np.ndarray:
    """Gera a matriz numérica isolada de NDVI usando NumPy."""
    shape = (60, 10, 10)
    vermelho = np.random.uniform(0.05, 0.25, shape)
    nir = np.random.uniform(0.30, 0.85, shape)
    ndvi = (nir - vermelho) / (nir + vermelho)
    return np.nanmean(ndvi, axis=(1, 2))


def processar_ia_modulo(service, ndvi, coordenada_gleba, estacoes, nitrogenio, possui_bpa, bloqueio_ambiental):
    """Executa a inferência matemática isolada sem depender do estado do objeto."""
    clima = service.interpolar_rbf(coordenada_gleba, estacoes)
    classificacao = service.classificar_cultura(ndvi)

    cultura = classificacao["cultura"]
    confianca = classificacao["confianca"]

    produtividade = service.calcular_produtividade(
        perfil_ndvi=ndvi,
        nitrogenio=nitrogenio,
        temperatura=clima["temperatura"],
        chuva=clima["chuva"]
    )

    if possui_bpa:
        produtividade *= 1.05

    if bloqueio_ambiental:
        produtividade = 0.0

    return clima, cultura, confianca, produtividade


# ==============================================================================
# CLASSE PRINCIPAL DO PIPELINE
# ==============================================================================
class VMGPipeline:

    def __init__(
            self,
            compliance_repo,   # 15 bases ambientais da portaria
            zarc_repo,         # Zoneamento oficial (Item n)
            solo_repo,         # Grid de Solo e dados de gleba
            clima_repo,        # Estações meteorológicas
            bpa_repo,          # Boas práticas agrícolas
            ledger_repo        # Blockchain/Hash Chain
    ):
        self.compliance_repo = compliance_repo
        self.zarc_repo = zarc_repo
        self.solo_repo = solo_repo
        self.clima_repo = clima_repo
        self.bpa_repo = bpa_repo
        self.ledger_repo = ledger_repo
        self.service = VMGIntelligenceService()

    async def executar(
            self,
            id_gleba: int,
            cultura_declarada: str,
            id_produtor: int = None,
            data_analise: pd.Timestamp = None
    ) -> Dict[str, Any]:

        loop = asyncio.get_running_loop()

        # Janela temporal de 60 meses da portaria
        if data_analise is None:
            data_analise = pd.Timestamp.now()

        limite_retroativo = pd.Timestamp.now() - pd.DateOffset(months=60)
        if data_analise < limite_retroativo:
            raise ValueError("Inconformidade com a Portaria: Auditorias limitadas aos últimos 60 meses.")

        base = data_analise - pd.DateOffset(months=3)
        safra = f"{base.year}/{base.year + 1}"

        # Controle de concorrência rigoroso para o SQLAlchemy AsyncSession
        lock = asyncio.Lock()

        async with lock:
            gleba = await self.solo_repo.obter_gleba(id_gleba)

        # Processamento do WKT Geométrico
        from shapely.wkt import loads
        geometria_texto = str(gleba["geometria"])
        poligono = loads(geometria_texto)
        centroide = poligono.centroid
        coordenada_gleba = [[float(centroide.x), float(centroide.y)]]

        # Cálculo do decêndio ZARC (1 a 36)
        data_plantio = pd.to_datetime(gleba.get("data_estimada_plantio") or data_analise)
        decendio_plantio = ((data_plantio.month - 1) * 3) + min(3, (data_plantio.day - 1) // 10 + 1)

        # Envelopamento das chamadas com Lock
        async def seguro_laudo_ambiental():
            async with lock:
                return await self.compliance_repo.verificar_restricoes_portaria(id_gleba, raio_metros=500.0)

        async def seguro_bpa():
            if not id_produtor:
                return False
            async with lock:
                return await self.service.validar_bpa(self.bpa_repo, id_produtor)

        async def seguro_zarc():
            async with lock:
                return await self.zarc_repo.validar_risco_climatico(id_gleba, cultura_declarada, decendio_plantio)

        async def seguro_nitrogenio():
            async with lock:
                return await self.service.obter_nitrogenio_medio(self.solo_repo, id_gleba)

        async def seguro_estacoes():
            async with lock:
                return await self.service.buscar_estacoes(self.clima_repo, id_gleba)

        async def seguro_hash():
            async with lock:
                return await self.ledger_repo.obter_ultimo_hash_gleba(id_gleba)

        # Orquestração paralela segura de I/O
        laudo_ambiental, possui_bpa, zarc_dados, nitrogenio, estacoes, hash_anterior = await asyncio.gather(
            seguro_laudo_ambiental(),
            seguro_bpa(),
            seguro_zarc(),
            seguro_nitrogenio(),
            seguro_estacoes(),
            seguro_hash()
        )

        bloqueio_ambiental = laudo_ambiental["conflito_socioambiental"]

        # CPU-Bound despachado invocando funções puras (Contorna o bug de atributo do Taskiq)
        ndvi = await loop.run_in_executor(None, rotina_numérica_ndvi)

        clima, cultura, confianca, produtividade = await loop.run_in_executor(
            None,
            processar_ia_modulo,
            self.service, ndvi, coordenada_gleba, estacoes, nitrogenio, possui_bpa, bloqueio_ambiental
        )

        # Montagem do bloco imutável
        payload = {
            "gleba_id": int(id_gleba),
            "safra": str(safra),
            "cultura": str(cultura),
            "cultura_declarada": str(cultura_declarada),
            "produtividade": float(round(produtividade, 2)),
            "nitrogenio": float(nitrogenio),
            "prodes": bool(laudo_ambiental["laudo_detalhado"]["conflito_prodes"]),
            "bloqueio_socioambiental": bool(bloqueio_ambiental),
            "bpa": bool(possui_bpa),
            "zarc_risco_admissivel": float(zarc_dados.get("risco_admissivel", 100.0))
        }

        hash_atual = self.service.gerar_hash(payload, hash_anterior)

        async with lock:
            await self.ledger_repo.salvar_bloco_ledger(
                dados_ia={**payload, "confianca": float(confianca)},
                hash_atual=str(hash_atual),
                hash_anterior=str(hash_anterior)
            )

        return {
            "gleba_id": int(id_gleba),
            "safra": str(safra),
            "classificacao": {
                "cultura_identificada": str(cultura),
                "confianca": float(confianca),
                "condizente_com_declarada": bool(cultura.upper() == cultura_declarada.upper())
            },
            "produtividade_sacas_ha": float(round(produtividade, 2)),
            "validacao_zarc": {
                "decendio_analisado": decendio_plantio,
                "tipo_solo": zarc_dados.get("tipo_solo", "N/A"),
                "risco_admissivel": zarc_dados.get("risco_admissivel", "FORA_DE_ZONEAMENTO")
            },
            "compliance_ambiental": {
                "aprovado": not bloqueio_ambiental,
                "laudo": laudo_ambiental["laudo_detalhado"]
            },
            "clima_interpolado": {
                "temperatura_c": float(clima["temperatura"]),
                "chuva_mm": float(clima["chuva"])
            },
            "ledger": {
                "hash_atual": str(hash_atual),
                "hash_anterior": str(hash_anterior)
            },
            "status": "OK"
        }
