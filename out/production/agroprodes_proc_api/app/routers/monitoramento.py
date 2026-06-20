import io
import os
import sys
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Query
import pystac_client
from rasterio.windows import from_bounds
from typing import Dict, Any
from app.dto.caderno import RespostaCadernoCampo

logger = logging.getLogger(__name__)
# ==============================================================================
# LIMPEZA E ISOLAMENTO GEOGRÁFICO DE AMBIENTE (DEVE SER A PRIMEIRA COISA DO ARQUIVO)
# ==============================================================================
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

if "venv" in sys.executable.lower():
    base_venv_path = Path(sys.executable).parent.parent
    proj_windows_path1 = base_venv_path / "Library" / "share" / "proj"
    proj_windows_path2 = base_venv_path / "Lib" / "site-packages" / "rasterio" / "proj_data"

    if proj_windows_path1.exists():
        os.environ["PROJ_LIB"] = str(proj_windows_path1)
        os.environ["PROJ_DATA"] = str(proj_windows_path1)
    elif proj_windows_path2.exists():
        os.environ["PROJ_LIB"] = str(proj_windows_path2)
        os.environ["PROJ_DATA"] = str(proj_windows_path2)

# ==============================================================================
# IMPORTS DAS BIBLIOTECAS QUE DEPENDEM DO PROJ CONFIGURADO
# ==============================================================================
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.io import MemoryFile

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# 🟢 CORREÇÃO: Importa a sessão assíncrona robusta que unifica os múltiplos schemas
from app.database.session import get_async_db

from app.dto.ClimaResponse import RespostaClimaticaHistorica
from app.services.clima_service import ClimaService
from app.services.produtividade_service import estimar_e_validar_produtividade
from rasterio.warp import transform_bounds
import cv2

router = APIRouter(prefix="/api/v1/mapa", tags=["Monitoramento MAPA"])

def gerar_geotiff_6_bandas_em_memoria(dados_bandas: dict, lat_centro: float, lon_centro: float) -> io.BytesIO:
    """
    Gera dinamicamente um arquivo GeoTIFF com 6 bandas espectrais estruturado na memória.
    Utiliza o padrão CRS EPSG:4326 exigido pelo termo de referência.
    """
    pixel_size = 0.0001
    height, width = 100, 100

    transform = from_origin(
        lon_centro - (width * pixel_size / 2),
        lat_centro + (height * pixel_size / 2),
        pixel_size,
        pixel_size
    )

    ordem_bandas = ['vermelho', 'nir', 'swir_1', 'red_edge_1', 'verde', 'azul']

    metadata = {
        'driver': 'GTiff',
        'dtype': 'float32',
        'nodata': -9999,
        'width': width,
        'height': height,
        'count': 6,
        'crs': 'EPSG:4326',
        'transform': transform
    }

    with MemoryFile() as memfile:
        with memfile.open(**metadata) as dst:
            for idx, nome_banda in enumerate(ordem_bandas, start=1):
                matriz_banda = dados_bandas.get(nome_banda)
                dst.write(matriz_banda, idx)
                dst.update_tags(idx, name=nome_banda.upper())

        return io.BytesIO(memfile.read())


def buscar_bandas_satelite_free(lat: float, lon: float) -> dict:
    """
    Recupera pixels reais de 6 bandas do Sentinel-2 via streaming (COG),
    lendo apenas a janela delimitada pelo bbox sem baixar a imagem inteira.
    """
    try:
        api_url = "https://earth-search.aws.element84.com/v1"
        catalogo = pystac_client.Client.open(api_url)

        bbox = [lon - 0.005, lat - 0.005, lon + 0.005, lat + 0.005]

        pesquisa = catalogo.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            max_items=3,
            query={"eo:cloud_cover": {"lt": 10}}
        )

        itens = list(pesquisa.items())
        if not itens:
            raise ValueError("Nenhuma imagem sem nuvens encontrada para esta região.")

        item_recente = itens[0]

        mapeamento_bandas = {
            'vermelho': 'red',
            'nir': 'nir',
            'swir_1': 'swir16',
            'red_edge_1': 'rededge1',
            'verde': 'green',
            'azul': 'blue'
        }

        dados_finais = {}

        config_streaming = {
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
            "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES"
        }

        with rasterio.Env(**config_streaming):
            for nome_interno, asset_id in mapeamento_bandas.items():
                if asset_id not in item_recente.assets:
                    raise KeyError(f"A banda {asset_id} não está disponível.")

                url_banda = item_recente.assets[asset_id].href

                with rasterio.open(url_banda) as src:
                    bbox_utm = transform_bounds("EPSG:4326", src.crs, *bbox)
                    janela_pixel = from_bounds(*bbox_utm, transform=src.transform)
                    matriz = src.read(1, window=janela_pixel)

                    if matriz.size == 0 or np.isnan(matriz).all():
                        matriz = np.zeros((100, 100), dtype=np.uint16)

                    if matriz.shape != (100, 100):
                        matriz = cv2.resize(matriz, (100, 100), interpolation=cv2.INTER_LINEAR)

                    matriz = np.nan_to_num(matriz, nan=0)
                    dados_finais[nome_interno] = matriz.astype(np.uint16)

        return dados_finais

    except Exception as e:
        raise RuntimeError(f"Falha ao obter dados via streaming: {str(e)}")


@router.get("/contrato/{id_contrato}/download-geotiff", response_class=StreamingResponse)
async def download_geotiff_contrato(
        id_contrato: int,
        db: AsyncSession = Depends(get_async_db)  # 🟢 CORREÇÃO: Sessão assíncrona unificada
):
    """
    Endpoint destinado ao MAPA para realizar o download de dados reais do Sentinel-2 em GeoTIFF.
    """
    try:
        query = text("""
                     SELECT g.id_gleba, ST_Y(ST_Centroid(g.geometria)) as lat, ST_X(ST_Centroid(g.geometria)) as lon, g.area_hectares
                     FROM agroprods.glebas g
                     WHERE g.id_gleba = :id_contrato;
                     """)

        result = await db.execute(query, {"id_contrato": id_contrato})
        dados_contrato = result.fetchone()

    except Exception as err_bd:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro de comunicação com o banco de dados geográfico: {str(err_bd)}"
        )

    if not dados_contrato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contrato ou Gleba monitorada de ID {id_contrato} não foi localizada."
        )

    try:
        lat_centro = float(dados_contrato.lat)
        lon_centro = float(dados_contrato.lon)

        dados_bandas_vmg = buscar_bandas_satelite_free(lat_centro, lon_centro)
        arquivo_geotiff = gerar_geotiff_6_bandas_em_memoria(dados_bandas_vmg, lat_centro, lon_centro)

        nome_arquivo = f"VMG_METADADOS_CONTRATO_{id_contrato}.tif"
        return StreamingResponse(
            arquivo_geotiff,
            media_type="image/tiff",
            headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no processamento do GeoTIFF: {str(e)}"
        )


    # =====================================================================
# 🟢 CONCLUSÃO: Rota Climatica Historica dos 60 meses da portaria
# =====================================================================
@router.get(
    "/contrato/{id_contrato}/analise-clima",
    response_model=RespostaClimaticaHistorica,
    status_code=status.HTTP_200_OK
)
async def consultar_analise_climatica_historica(
        id_contrato: int,
        cultura: str = Query("SOJA", description="Cultura alvo para calibração dos limiares da portaria"),
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Retorna o histórico climático interpolado dos últimos 60 meses da gleba
    para atendimento das regras semestrais de auditoria da portaria (Item 3.8.b).
    """
    logger.info(f"Iniciando auditoria de histórico climático para o contrato/gleba {id_contrato}.")
    try:
        # Instancia o serviço unificado passando a sessão assíncrona do banco
        service = ClimaService(db)

        # CORREÇÃO CRÍTICA: Passa os parâmetros corretos exigidos pelo método vetorizado do Service
        historico_clima = await service.processar_historico_climatico_60_meses(
            id_gleba=id_contrato,
            cultura=cultura
        )

        return historico_clima

    except ValueError as val_err:
        logger.warning(f"Gleba inválida ou não mapeada: {str(val_err)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err)
        )
    except Exception as e:
        logger.error(f"Falha crítica ao consolidar histórico climático de 60 meses: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao consolidar histórico climático retroativo de 60 meses."
        )


# =====================================================================
# 📘 ROTA: Caderno de Campo Individualizado por Safra (Item 3.c.XII)
# =====================================================================
@router.get(
    "/contrato/{id_contrato}/caderno-campo",
    response_model=RespostaCadernoCampo,
    status_code=status.HTTP_200_OK
)
async def obter_caderno_campo_safra(
        id_contrato: int,
        db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Fornece ao final do monitoramento um caderno de campo individualizado com as informações
    mais relevantes identificadas durante a safra e sua estimativa de produtividade.
    """
    logger.info(f"Gerando caderno de campo individualizado para a gleba {id_contrato}.")
    try:
        # 1. Recupera as informações básicas cadastrais e os resultados reais consolidados no Ledger
        query_dados = text("""
                           SELECT g.id_gleba, g.area_hectares, cl.cultura_identificada, cl.percentual_confianca,
                                  cl.safra, pr.produtividade_ia_sacas_ha, pr.volume_comercializar_declarado,
                                  TO_CHAR(d.data_estimada_plantio, 'YYYY-MM-DD') as d_plantio,
                                  TO_CHAR(d.data_estimada_colheita, 'YYYY-MM-DD') as d_colheita
                           FROM agroprods.glebas g
                                    JOIN audit.ia_classificacao_cultura_ledger cl ON g.id_gleba = cl.id_gleba
                                    JOIN audit.ia_estimativa_produtividade_ledger pr ON g.id_gleba = pr.id_gleba AND cl.hash_bloco = pr.hash_bloco
                                    JOIN audit.declaracao_gleba_periodo_ledger d ON g.id_gleba = d.id_gleba AND cl.hash_bloco = d.hash_bloco
                           WHERE g.id_gleba = :id
                           ORDER BY cl.data_analise DESC
                               LIMIT 1;
                           """)
        res = await db.execute(query_dados, {"id": id_contrato})
        registro = res.fetchone()

        if not registro:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Gleba ou registros de auditoria do Ledger não localizados no sistema."
            )

        # 2. Reutiliza o motor de clima de 60 meses passando o ID do contrato de forma limpa e performática
        clima_service = ClimaService(db)
        clima = await clima_service.processar_historico_climatico_60_meses(
            id_gleba=id_contrato,
            cultura=registro.cultura_identificada
        )

        # 3. Lógica matemática de validação de volume condizente (Evita dependência de funções mockadas externas)
        volume_estimado_total = float(registro.area_hectares) * float(registro.produtividade_ia_sacas_ha)
        volume_declarado_condizente = bool(float(registro.volume_comercializar_declarado) <= (volume_estimado_total * 1.10))

        # 4. Monta o payload unificado em conformidade estrita com o edital do MAPA e Schema Pydantic
        return {
            "id_gleba": id_contrato,
            "safra_ano": registro.safra,
            "area_hectares": float(registro.area_hectares),
            "analise_vegetativa_ia": {
                "cultura_identificada": registro.cultura_identificada,
                "assertividade_score": float(registro.percentual_confianca),
                "data_estimada_plantio": registro.d_plantio,
                "data_estimada_colheita": registro.d_colheita
            },
            "diagnostico_climatico": clima.get("indicadores_acumulados", {}),
            "alertas_ambientais_emitidos": clima.get("alertas_emitidos", []),
            "validacao_comercial": {
                "produtividade_estimada_sc_ha": float(registro.produtividade_ia_sacas_ha),
                "volume_total_estimado_sacas": round(volume_estimado_total, 2),
                "volume_declarado_condizente": volume_declarado_condizente
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro crítico ao compilar caderno de campo para a gleba {id_contrato}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no servidor ao consolidar o relatório do caderno de campo."
        )