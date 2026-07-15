import asyncio
from datetime import datetime
import numpy as np
import pandas as pd
from typing import Dict, Any

import rasterio
from rasterio.mask import mask
from shapely.wkt import loads
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

logger = logging.getLogger(__name__)


# ==============================================================================
# FUNÇÕES PURAS ISOLADAS (Otimizadas para Processamento em Bloco e Rede)
# ==============================================================================

def calcular_ndvi_real(rasters, geometria_wkt: str):
    """
    Calcula o NDVI em lote via streaming de imagens de satélite (Cloud Optimized GeoTIFFs).
    Aprimorado com tratamento fino de erros do GDAL e timeout.
    """
    from shapely.ops import transform as shapely_transform
    from pyproj import Transformer
    from shapely.geometry import mapping
    import numpy as np
    import rasterio
    from rasterio.mask import mask

    geometria = loads(geometria_wkt)
    resultados = []

    # Configurações de performance de rede refinadas para evitar timeouts e travamentos de requisição
    gdal_config = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_TIMEOUT": "15",  # Limite de 15s por requisição
        "GDAL_HTTP_MAX_RETRY": "3",  # Tenta novamente em caso de flutuação de rede
        "GDAL_HTTP_RETRY_DELAY": "2",  # Intervalo de re-tentativa
        "VSI_CACHE": "TRUE",  # Habilita cache de leitura em memória
        "VSI_CACHE_SIZE": "50000000",  # 50MB de cache virtual
        "CPL_DEBUG": "OFF"  # Mude para ON localmente se precisar depurar conexões HTTP profundas
    }

    # Ativa ambiente de execução seguro do GDAL
    with rasterio.Env(**gdal_config):
        for r in rasters:
            url_composta = r.get("raster_url")
            id_raster = r.get("id_raster")

            if not url_composta:
                logger.warning(f"URL inválida ou nula para o raster {id_raster}.")
                continue

            # Extração segura das bandas científica de Red e NIR
            if "|" in url_composta:
                url_red, url_nir = url_composta.split("|")
            else:
                url_visual = url_composta
                url_red = url_visual.replace("visual.tif", "B04.tif")
                url_nir = url_visual.replace("visual.tif", "B08.tif")

            try:
                # 1. Processamento e leitura da banda Vermelha (Red)
                with rasterio.open(url_red) as src_red:
                    crs = src_red.crs
                    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
                    geom_proj = shapely_transform(transformer.transform, geometria)
                    geoms = [mapping(geom_proj)]

                    red_mask, _ = mask(src_red, geoms, crop=True, filled=False, nodata=np.nan)
                    red_array = red_mask[0].astype(np.float32)

                # 2. Processamento e leitura da banda Infravermelho Próximo (NIR)
                with rasterio.open(url_nir) as src_nir:
                    nir_mask, _ = mask(src_nir, geoms, crop=True, filled=False, nodata=np.nan)
                    nir_array = nir_mask[0].astype(np.float32)

                # 3. Cálculo do NDVI vetorizado com descarte seguro de divisão por zero e ruídos
                denominador = nir_array + red_array
                numerador = nir_array - red_array

                with np.errstate(divide='ignore', invalid='ignore'):
                    ndvi_matriz = np.where(denominador == 0, np.nan, numerador / denominador)

                # Filtro físico do espectro de reflectância do NDVI válido
                ndvi_matriz = np.where((ndvi_matriz >= -1.0) & (ndvi_matriz <= 1.0), ndvi_matriz, np.nan)
                pixels_validos = ndvi_matriz[~np.isnan(ndvi_matriz)]

                if pixels_validos.size > 0:
                    mean_val = float(np.mean(pixels_validos))
                    std_val = float(np.std(pixels_validos))
                else:
                    mean_val, std_val = 0.0, 0.0

                resultados.append({
                    "id_raster": id_raster,
                    "data": r["data_captura"],
                    "ndvi_mean": mean_val,
                    "ndvi_std": std_val
                })

            except Exception as ex:
                # LOG EXPLÍCITO DO MOTIVO DO FRACASSO DO DOWNLOAD/LEITURA
                logger.error(
                    f"Falha ao realizar streaming ou processamento do raster {id_raster} via COG. "
                    f"URLs testadas: [RED: {url_red}] | [NIR: {url_nir}]. Erro: {str(ex)}"
                )
                continue

    return resultados


def processar_ia_modulo(service, ndvi, coordenada_gleba, estacoes, nitrogenio, possui_bpa, bloqueio_ambiental):
    """Executa a inferência matemática isolada sem depender de contexto corrompível do Taskiq."""
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

    def __init__(self, compliance_repo, zarc_repo, solo_repo, clima_repo, bpa_repo, ledger_repo, db_session):
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

        # 2. Define a janela operacional e corrige a safra dinamicamente
        if data_plantio > agora:
            logger.warning(
                f"Plantio programado para o futuro ({data_plantio.date()}). Ajustando busca para o histórico fenológico (180 dias).")
            dt_inicio = (agora - pd.DateOffset(days=180)).to_pydatetime()
            dt_fim = agora

            base_historica = agora - pd.DateOffset(months=6)
            safra = f"{base_historica.year}/{base_historica.year + 1}"
        else:
            limite_inicio = (data_plantio - pd.DateOffset(days=30)).to_pydatetime()
            limite_fim = data_analise.to_pydatetime()

            dt_inicio = min(limite_inicio, agora)
            dt_fim = min(limite_fim, agora)
            if dt_inicio > dt_fim:
                dt_inicio, dt_fim = dt_fim, dt_inicio

            base = data_plantio - pd.DateOffset(months=3)
            safra = f"{base.year}/{base.year + 1}"

        if (dt_fim - dt_inicio).days < 5:
            dt_inicio = (dt_fim - pd.DateOffset(days=180)).to_pydatetime()

        logger.info(
            f"Buscando rasters VMG na janela operacional: {dt_inicio.date()} até {dt_fim.date()} para a Safra: {safra}")

        # Busca registros de metadados no Postgres
        rasters = await self.solo_repo.buscar_rasters(
            id_gleba=id_gleba,
            data_inicio=dt_inicio,
            data_fim=dt_fim,
        )

        if not rasters:
            # Sincroniza via STAC client (gera os registros de metadados vazios no banco com as URLs corretas de download)
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
                "Nenhum raster cadastrado ou sincronizado para a gleba no período informado."
            )

        geometria_texto = str(gleba["geometria"])
        poligono = loads(geometria_texto)
        centroide = poligono.centroid
        coordenada_gleba = [[float(centroide.x), float(centroide.y)]]

        # Determina os decêndios da portaria MAPA / ZARC
        if data_plantio.day <= 10:
            decendio_mes = 1
        elif data_plantio.day <= 20:
            decendio_mes = 2
        else:
            decendio_mes = 3

        decendio_plantio = ((data_plantio.month - 1) * 3) + decendio_mes

        laudo_ambiental = await self.compliance_repo.verificar_restricoes_portaria(id_gleba, raio_metros=500.0)
        possui_bpa = await self.service.validar_bpa(self.bpa_repo, id_produtor)
        zarc_dados = await self.zarc_repo.validar_risco_climatico(id_gleba, cultura_declarada, decendio_plantio)
        nitrogenio = await self.service.obter_nitrogenio_medio(self.solo_repo, id_gleba)
        estacoes = await self.service.buscar_estacoes(self.clima_repo, id_gleba)

        hash_anterior = await self.ledger_repo.obter_ultimo_hash_gleba(id_gleba)
        bloqueio_ambiental = laudo_ambiental["conflito_socioambiental"]

        # ----------------------------------------------------------------------
        # LÓGICA DE CACHE E CÁLCULO DE NDVI ASSÍNCRONO / SEGURO
        # ----------------------------------------------------------------------
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
            logger.info(f"Processando download/cálculo por streaming de {len(rasters_para_calcular)} rasters.")

            # Libera o Event Loop enquanto o threadpool do rasterio faz as requisições HTTP demoradas
            novos_calculos = await loop.run_in_executor(
                None,
                calcular_ndvi_real,
                rasters_para_calcular,
                geometria_texto,
            )

            if not novos_calculos:
                logger.error("Todos os cálculos de NDVI retornaram vazios ou falharam por erro de rede.")
            else:
                ndvi_resultados.extend(novos_calculos)

                # Persistência atômica isolada para evitar transações longas travando a conexão do Postgres
                try:
                    for calculo in novos_calculos:
                        await self.solo_repo.atualizar_estatisticas_ndvi(
                            id_raster=calculo["id_raster"],
                            ndvi_mean=calculo["ndvi_mean"],
                            ndvi_std=calculo["ndvi_std"]
                        )
                    # Força a gravação dos dados no banco imediatamente liberando o pool
                    await self.db_session.flush()
                except Exception as db_ex:
                    logger.exception(
                        "Falha ao salvar cache de NDVI no banco de dados. Tentando realizar rollback seguro.")
                    await self.db_session.rollback()

        if not ndvi_resultados:
            raise ValueError(
                "Falha crítica: Não há dados válidos de NDVI calculados para esta gleba."
            )

        # Ordenação cronológica estrita da série temporal
        ndvi_resultados.sort(key=lambda x: x["data"])

        # Execução do modelo inteligente de predição
        clima, cultura, confianca, produtividade = await loop.run_in_executor(
            None,
            processar_ia_modulo,
            self.service, ndvi_resultados, coordenada_gleba, estacoes, nitrogenio, possui_bpa, bloqueio_ambiental
        )

        payload_ndvi_json = [
            {"data": str(item["data"]), "ndvi_mean": float(item["ndvi_mean"]), "ndvi_std": float(item["ndvi_std"])}
            for item in ndvi_resultados
        ]

        if cultura.upper() == cultura_declarada.upper() and confianca >= 0.75:
            await self.solo_repo.salvar_dados_para_treinamento(
                gleba_id=id_gleba,
                safra=safra,
                ndvi=payload_ndvi_json,
                cultura_real=cultura.upper()
            )

        # Montagem do payload seguro do ledger imutável
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
            risco_zarc_admissivel=float(zarc_dados.get("risco_admissivel", 40.0)),
            possui_certificado_bpa=bool(possui_bpa),
            hash_bloco=str(hash_atual)
        )

        self.db_session.add_all([laudo_ledger, classificacao_ledger, produtividade_ledger, declaracao_ledger])

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