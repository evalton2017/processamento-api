import asyncio
from datetime import datetime

import numpy as np
import pandas as pd
from typing import Dict, Any

import rasterio
from rasterio.io import MemoryFile
from rasterio.mask import mask
# Este lê strings WKT como 'POLYGON ((...))'
from shapely.wkt import loads

# Este importa apenas o que realmente existe em geometry
from shapely.geometry import mapping

from app.services.pipelineia.vmg_intelligence_service import VMGIntelligenceService
from app.models.models_ledger import (
    IaClassificacaoCulturaLedger,
    IaEstimativaProdutividadeLedger,
    HistoricoLaudosAmbientaisLedger,
    DeclaracaoGlebaPeriodoLedger
)
from app.events.vmg_events import vmg_event_dispatcher, EventoAnaliseConcluida

import logging

#logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ==============================================================================
# FUNÇÕES PURAS ISOLADAS (Protegidas contra corrupção de cache do Taskiq)
# ==============================================================================
def processar_raster(
        dataset,
        geometria,
        banda_red=None,
        banda_nir=None,
):
    try:
        if banda_red is None or banda_nir is None:
            if dataset.count >= 8:
                banda_red = 4
                banda_nir = 8
            elif dataset.count >= 2:
                banda_red = 1
                banda_nir = 2
            else:
                raise ValueError(
                    f"Raster incompatível ({dataset.count} bandas)"
                )

            logger.info("CRS: %s", dataset.crs)
            logger.info("Transform: %s", dataset.transform)
            logger.info("Bounds: %s", dataset.bounds)
            logger.info("Profile: %s", dataset.profile)
        bandas, _ = mask(
            dataset,
            [mapping(geometria)],
            crop=True,
            indexes=[banda_red, banda_nir],
            filled=False,
        )
        red = bandas[0].astype(np.float32)
        nir = bandas[1].astype(np.float32)
        if dataset.nodata is not None:
            red = np.where(
                red == dataset.nodata,
                np.nan,
                red,
                )
            nir = np.where(
                nir == dataset.nodata,
                np.nan,
                nir,
                )
        soma = nir + red
        ndvi = np.divide(
            nir - red,
            soma,
            out=np.full(
                red.shape,
                np.nan,
                dtype=np.float32,
            ),
            where=soma != 0,
            )
        ndvi = np.clip(
            ndvi,
            -1,
            1,
        )
        return float(np.nanmean(ndvi))
    except Exception:
        logger.exception(
            "Erro no processamento raster"
        )
        return np.nan

def calcular_ndvi_real(rasters, geometria_wkt: str):
    import rasterio
    import numpy as np
    from rasterio.mask import mask
    from shapely.ops import transform as shapely_transform
    from pyproj import Transformer
    from shapely.geometry import mapping

    geometria = loads(geometria_wkt)
    resultados = []

    # Configuração de performance para streaming do GDAL/Rasterio
    gdal_env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"
    )

    with gdal_env:
        for r in rasters:
            try:
                url_composta = r["raster_url"]

                # Se a URL contiver o separador, extrai os links científicos corretos
                if "|" in url_composta:
                    url_red, url_nir = url_composta.split("|")
                else:
                    # Fallback de segurança se o registro for antigo
                    url_visual = url_composta
                    url_red = url_visual.replace("visual.tif", "B04.tif")
                    url_nir = url_visual.replace("visual.tif", "B08.tif")

                # Abre a banda Red para coletar a projeção (CRS)
                with rasterio.open(url_red) as src_red:
                    crs = src_red.crs

                    # Projeta a gleba (WGS84) para o CRS do raster (UTM local da imagem)
                    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
                    geom_proj = shapely_transform(transformer.transform, geometria)
                    geoms = [mapping(geom_proj)]

                    # Recorta via streaming apenas os pixels internos da gleba
                    red_mask, _ = mask(src_red, geoms, crop=True, filled=False, nodata=np.nan)
                    red_array = red_mask[0].astype(np.float32)

                with rasterio.open(url_nir) as src_nir:
                    nir_mask, _ = mask(src_nir, geoms, crop=True, filled=False, nodata=np.nan)
                    nir_array = nir_mask[0].astype(np.float32)

                # Cálculo seguro do NDVI ignorando o nodata/nan
                denominador = nir_array + red_array
                numerador = nir_array - red_array

                # Evita divisão por zero
                with np.errstate(divide='ignore', invalid='ignore'):
                    ndvi_matriz = np.where(denominador == 0, np.nan, numerador / denominador)

                # Filtra valores fora do range válido do NDVI por ruído atmosférico
                ndvi_matriz = np.where((ndvi_matriz >= -1.0) & (ndvi_matriz <= 1.0), ndvi_matriz, np.nan)

                # Remove máscaras e gera estatísticas limpas
                pixels_validos = ndvi_matriz[~np.isnan(ndvi_matriz)]

                if pixels_validos.size > 0:
                    mean_val = float(np.mean(pixels_validos))
                    std_val = float(np.std(pixels_validos))
                else:
                    mean_val, std_val = 0.0, 0.0

                resultados.append({
                    "id_raster": r["id_raster"],
                    "data": r["data_captura"],
                    "ndvi_mean": mean_val,
                    "ndvi_std": std_val
                })

            except Exception as e:
                # Se falhar uma imagem (ex: link expirado ou nuvem excessiva oculta as bandas), continua o loop
                continue

    return resultados

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

    def __init__(self,compliance_repo,zarc_repo,solo_repo,clima_repo,bpa_repo,ledger_repo, db_session
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

        gleba = await self.solo_repo.obter_gleba(id_gleba)

        # 1. Recupera as datas base
        data_plantio = pd.to_datetime(
            gleba.get("data_estimada_plantio") or data_analise
        )
        agora = datetime.now()

        # 2. DEFINE A JANELA OPERACIONAL E CORRIGE A SAFRA DINAMICAMENTE
        if data_plantio > agora:
            logger.warning(f"Plantio programado para o futuro ({data_plantio.date()}). Ajustando busca para o histórico fenológico (180 dias).")

            # Se o plantio está no futuro, a IA vai avaliar o histórico real que aconteceu nos últimos 180 dias
            dt_inicio = (agora - pd.DateOffset(days=180)).to_pydatetime()
            dt_fim = agora

            # CORREÇÃO DA SAFRA: Como estamos olhando o passado real (fim de 2025/início de 2026), a safra é a anterior
            base_historica = agora - pd.DateOffset(months=6)
            safra = f"{base_historica.year}/{base_historica.year + 1}"  # Fica "2025/2026"
        else:
            # SE O PLANTIO JÁ OCORREU: Usa a janela normal do ciclo atual
            limite_inicio = (data_plantio - pd.DateOffset(days=30)).to_pydatetime()
            limite_fim = data_analise.to_pydatetime()

            dt_inicio = min(limite_inicio, agora)
            dt_fim = min(limite_fim, agora)
            if dt_inicio > dt_fim:
                dt_inicio, dt_fim = dt_fim, dt_inicio

            # Safra normal baseada no plantio real que já aconteceu
            base = data_plantio - pd.DateOffset(months=3)
            safra = f"{base.year}/{base.year + 1}"

        # 3. Margem de segurança caso o intervalo fique estreito demais
        if (dt_fim - dt_inicio).days < 5:
            dt_inicio = (dt_fim - pd.DateOffset(days=180)).to_pydatetime()

        logger.info(f"Buscando rasters VMG na janela operacional: {dt_inicio.date()} até {dt_fim.date()} para a Safra: {safra}")

        rasters = await self.solo_repo.buscar_rasters(
            id_gleba=id_gleba,
            data_inicio=dt_inicio,
            data_fim=dt_fim,
        )

        if not rasters:
            # Passa objetos datetime nativos e limpos para evitar quebras no pystac_client
            await self.service.sincronizar_rasters_gleba(
                solo_repo=self.solo_repo,
                geometria_wkt=gleba["geometria"],
                id_gleba=id_gleba,
                data_inicio=dt_inicio,
                data_fim=dt_fim,
            )
            rasters = await self.solo_repo.buscar_rasters(
                id_gleba=id_gleba,
                data_inicio=dt_inicio,
                data_fim=dt_fim,
            )

        if not rasters:
            raise ValueError(
                "Nenhum raster encontrado para a gleba no período informado."
            )

        geometria_texto = str(gleba["geometria"])
        poligono = loads(geometria_texto)
        centroide = poligono.centroid
        coordenada_gleba = [[float(centroide.x), float(centroide.y)]]

        # Cálculo do decêndio ZARC (1 a 36)
        decendio_plantio = ((data_plantio.month - 1) * 3) + min(3, (data_plantio.day - 1) // 10 + 1)

        laudo_ambiental = await self.compliance_repo.verificar_restricoes_portaria(id_gleba, raio_metros=500.0)
        possui_bpa = await self.service.validar_bpa(self.bpa_repo, id_produtor)
        zarc_dados = await self.zarc_repo.validar_risco_climatico(id_gleba, cultura_declarada, decendio_plantio)
        nitrogenio = await self.service.obter_nitrogenio_medio(self.solo_repo, id_gleba)
        estacoes = await self.service.buscar_estacoes(self.clima_repo, id_gleba)

        hash_anterior = await self.ledger_repo.obter_ultimo_hash_gleba(id_gleba)
        bloqueio_ambiental = laudo_ambiental["conflito_socioambiental"]

        # LÓGICA REESTRUTURADA: Cache Híbrido de NDVI via COG
        ndvi_resultados = []
        rasters_para_calcular = []

        for r in rasters:
            if r.get("ndvi_mean") is not None and r.get("ndvi_std") is not None:
                ndvi_resultados.append({
                    "id_raster": r["id_raster"],
                    "data": r["data_captura"],
                    "ndvi_mean": r["ndvi_mean"],
                    "ndvi_std": r["ndvi_std"]
                })
            else:
                rasters_para_calcular.append(r)

        if rasters_para_calcular:
            novos_calculos = await loop.run_in_executor(
                None,
                calcular_ndvi_real,
                rasters_para_calcular,
                geometria_texto,
            )

            ndvi_resultados.extend(novos_calculos)

            for calculo in novos_calculos:
                await self.solo_repo.atualizar_estatisticas_ndvi(
                    id_raster=calculo["id_raster"],
                    ndvi_mean=calculo["ndvi_mean"],
                    ndvi_std=calculo["ndvi_std"]
                )

        # Ordena a série temporal para a IA processar em ordem cronológica estrita
        ndvi_resultados.sort(key=lambda x: x["data"])
        # Execução do módulo de Inteligência Artificial usando a lista final de estatísticas
        clima, cultura, confianca, produtividade = await loop.run_in_executor(
            None,
            processar_ia_modulo,
            self.service, ndvi_resultados, coordenada_gleba, estacoes, nitrogenio, possui_bpa, bloqueio_ambiental
        )
        payload_ndvi_json = [
            {"data": str(item["data"]), "ndvi_mean": float(item["ndvi_mean"]), "ndvi_std": float(item["ndvi_std"])}
            for item in ndvi_resultados
        ]

        # Se a IA bater com a declaração do produtor, temos um dado de treino perfeito (Ground Truth Confiável)
        if cultura.upper() == cultura_declarada.upper() and confianca >= 0.75:
            await self.solo_repo.salvar_dados_para_treinamento(
                gleba_id=id_gleba,
                safra=safra,
                ndvi=payload_ndvi_json,
                cultura_real=cultura.upper()
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
            data_estimada_plantio=data_plantio.to_pydatetime(),
            data_estimada_colheita=pd.to_datetime(gleba.get("data_estimated_colheita") or data_analise).to_pydatetime(),
            decendio_plantio_zarc=int(decendio_plantio),
            risco_zarc_admissivel=float(zarc_dados.get("risco_admissivel", 100.0)),
            possui_certificado_bpa=bool(possui_bpa),
            hash_bloco=str(hash_atual)
        )

        self.db_session.add_all([laudo_ledger, classificacao_ledger, produtividade_ledger, declaracao_ledger])

        # Disparo de ouvintes de eventos de negócio
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
