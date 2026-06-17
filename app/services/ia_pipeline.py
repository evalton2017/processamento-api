import asyncio
import numpy as np
import pandas as pd
from typing import Dict, Any
from shapely.wkt import loads

from app.services.vmg_intelligence_service import VMGIntelligenceService
from app.models.models_ledger import (
    IaClassificacaoCulturaLedger,
    IaEstimativaProdutividadeLedger,
    HistoricoLaudosAmbientaisLedger,
    DeclaracaoGlebaPeriodoLedger
)
from app.events.vmg_events import vmg_event_dispatcher, EventoAnaliseConcluida

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
            compliance_repo,
            zarc_repo,
            solo_repo,
            clima_repo,
            bpa_repo,
            ledger_repo,
            db_session
    ):
        self.compliance_repo = compliance_repo
        self.zarc_repo = zarc_repo
        self.solo_repo = solo_repo
        self.clima_repo = clima_repo
        self.bpa_repo = bpa_repo
        self.ledger_repo = ledger_repo
        self.db_session = db_session
        self.service = VMGIntelligenceService()

    async def executar(
            self,
            id_gleba: int,
            cultura_declarada: str,
            id_produtor: int,
            data_analise: pd.Timestamp = None
    ) -> Dict[str, Any]:

        loop = asyncio.get_running_loop()

        if data_analise is None:
            data_analise = pd.Timestamp.now()

        limite_retroativo = pd.Timestamp.now() - pd.DateOffset(months=60)
        if data_analise < limite_retroativo:
            raise ValueError("Inconformidade com a Portaria: Auditorias limitadas aos últimos 60 meses.")

        base = data_analise - pd.DateOffset(months=3)
        safra = f"{base.year}/{base.year + 1}"

        gleba = await self.solo_repo.obter_gleba(id_gleba)

        geometria_texto = str(gleba["geometria"])
        poligono = loads(geometria_texto)
        centroide = poligono.centroid
        coordenada_gleba = [[float(centroide.x), float(centroide.y)]]
       # Cálculo do decêndio ZARC (1 a 36)
        data_plantio = pd.to_datetime(gleba.get("data_estimada_plantio") or data_analise)
        decendio_plantio = ((data_plantio.month - 1) * 3) + min(3, (data_plantio.day - 1) // 10 + 1)

        laudo_ambiental = await self.compliance_repo.verificar_restricoes_portaria(id_gleba, raio_metros=500.0)
        possui_bpa = await self.service.validar_bpa(self.bpa_repo, id_produtor)
        zarc_dados = await self.zarc_repo.validar_risco_climatico(id_gleba, cultura_declarada, decendio_plantio)
        nitrogenio = await self.service.obter_nitrogenio_medio(self.solo_repo, id_gleba)
        estacoes = await self.service.buscar_estacoes(self.clima_repo, id_gleba)

        # Chamadas externas ou isoladas que não conflitam com a sessão principal
        hash_anterior = await self.ledger_repo.obter_ultimo_hash_gleba(id_gleba)

        bloqueio_ambiental = laudo_ambiental["conflito_socioambiental"]

        # CPU-Bound despachado em Threads para não congelar o Event Loop assíncrono
        ndvi = await loop.run_in_executor(None, rotina_numérica_ndvi)

        clima, cultura, confianca, produtividade = await loop.run_in_executor(
            None,
            processar_ia_modulo,
            self.service, ndvi, coordenada_gleba, estacoes, nitrogenio, possui_bpa, bloqueio_ambiental
        )

        # Montagem do payload base do bloco imutável
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

        # Cálculo criptográfico encadeado usando o encoder robusto
        hash_atual = self.service.gerar_hash(payload, hash_anterior)

        laudo_ledger = HistoricoLaudosAmbientaisLedger(
            id_gleba=id_gleba,
            conflito_socioambiental=bool(bloqueio_ambiental),
            conflito_prodes=bool(laudo_ambiental["laudo_detalhado"]["conflito_prodes"]),
            conflito_ibama_icmbio=bool(laudo_ambiental["laudo_detalhado"].get("conflito_embargos", False)),
            conflito_comunidades=bool(laudo_ambiental["laudo_detalhado"].get("conflito_comunidades", False)),
            laudo_detalhado_json=laudo_ambiental["laudo_detalhado"],
            hash_bloco=str(hash_atual)
        )

        classificacao_ledger = IaClassificacaoCulturaLedger(
            id_gleba=id_gleba,
            safra=str(safra),
            cultura_identificada=str(cultura),
            cultura_declarada=str(cultura_declarada),
            status_conducao="CONDIZENTE" if cultura.upper() == cultura_declarada.upper() else "DIVERGENTE",
            percentual_confianca=float(confianca),
            hash_bloco=str(hash_atual)
        )

        produtividade_ledger = IaEstimativaProdutividadeLedger(
            id_gleba=id_gleba,
            safra=str(safra),
            produtividade_ia_sacas_ha=float(round(produtividade, 2)),
            volume_comercializar_declarado=float(gleba.get("volume_declarado_comercializar", 0.0)),
            status_compatibilidade="APROVADO" if not bloqueio_ambiental else "BLOQUEADO",
            hash_bloco=str(hash_atual)
        )

        declaracao_ledger = DeclaracaoGlebaPeriodoLedger(
            id_gleba=id_gleba,
            id_produtor=id_produtor,
            cultura_declarada=str(cultura_declarada),
            data_estimada_plantio=data_plantio,
            data_estimada_colheita=pd.to_datetime(gleba.get("data_estimada_colheita") or data_analise),
            decendio_plantio_zarc=int(decendio_plantio),
            risco_zarc_admissivel=float(zarc_dados.get("risco_admissivel", 100.0)),
            possui_certificado_bpa=bool(possui_bpa),
            hash_bloco=str(hash_atual)
        )

        self.db_session.add_all([laudo_ledger, classificacao_ledger, produtividade_ledger, declaracao_ledger])

        # DESACOPLAMENTO CRÍTICO: Disparo de ouvintes de eventos de negócio
        evento = EventoAnaliseConcluida(
            id_produtor=id_produtor,
            id_gleba=id_gleba,
            cultura_declarada=cultura_declarada,
            cultura_identificada=cultura,
            confianca=confianca,
            produtividade=produtividade,
            bloqueio_ambiental=bloqueio_ambiental
        )
        await vmg_event_dispatcher.disparar(evento, self.db_session)

        await self.ledger_repo.salvar_bloco_ledger(
            dados_ia={**payload, "confianca": float(confianca)},
            hash_atual=str(hash_atual)
        )

        # Força a sincronização dos dados no banco sem encerrar a transação
        await self.db_session.flush()

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
