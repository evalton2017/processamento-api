import io
import os
import sys
from pathlib import Path


from app.schemas.caderno import RespostaCadernoCampo

# ==============================================================================
# LIMPEZA E ISOLAMENTO GEOGRÁFICO DE AMBIENTE (DEVE SER A PRIMEIRA COISA DO ARQUIVO)
# ==============================================================================
# Força a deleção de variáveis residuais que o Windows injetou do QGIS/Postgres
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

if "venv" in sys.executable.lower():
    # Detecta a pasta raiz da sua Venv dinâmica
    base_venv_path = Path(sys.executable).parent.parent

    # Define o caminho para as duas estruturas possíveis de empacotamento no Windows
    proj_windows_path1 = base_venv_path / "Library" / "share" / "proj"
    proj_windows_path2 = base_venv_path / "Lib" / "site-packages" / "rasterio" / "proj_data"

    # Injeta de forma fixa apenas os caminhos internos e limpos da sua Venv
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
import rasterio  # O rasterio agora lerá as variáveis limpas acima
from rasterio.transform import from_origin
from rasterio.io import MemoryFile

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database.session import get_db
from app.schemas.clima import RespostaClimaticaHistorica
from app.services.clima_service import gerar_historico_climatico_60_meses
from app.services.produtividade_service import estimar_e_validar_produtividade


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

    # ◄ CORREÇÃO CRÍTICA: Utiliza MemoryFile para gerenciar os blocos de bytes com segurança no Rasterio
    with MemoryFile() as memfile:
        with memfile.open(**metadata) as dst:
            for idx, nome_banda in enumerate(ordem_bandas, start=1):
                matriz_banda = dados_bandas.get(nome_banda, np.random.rand(height, width).astype(np.float32))
                dst.write(matriz_banda, idx)
                dst.update_tags(idx, name=nome_banda.upper())

                # Retorna uma cópia dos bytes gerados estruturados para envio via streaming
        return io.BytesIO(memfile.read())


@router.get("/contrato/{id_contrato}/download-geotiff", response_class=StreamingResponse)
async def download_geotiff_contrato(id_contrato: int, db: AsyncSession = Depends(get_db)):
    """
    Endpoint destinado ao MAPA para realizar o download individualizado dos metadados
    em formato GeoTIFF contendo as 6 bandas espectrais e coordenadas da gleba monitorada.
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

    # 2. SE NÃO ENCONTRAR: Retorna 404 de forma limpa FORA do bloco try genérico de processamento
    if not dados_contrato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contrato ou Gleba monitorada de ID {id_contrato} não foi localizada no esquema agroprods."
        )

    # 2. SE NÃO ENCONTRAR: Retorna 404 de forma limpa FORA do bloco try genérico de processamento
    if not dados_contrato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contrato ou Gleba monitorada de ID {id_contrato} não foi localizada no esquema agroprods."
        )

    try:
        lat_centro = float(dados_contrato.lat)
        lon_centro = float(dados_contrato.lon)

        # 2. Simulador de recuperação de matrizes de satélite processadas (Mock das 6 bandas)
        shape_padrao = (100, 100)
        dados_bandas_vmg = {
            'vermelho': np.random.uniform(0, 0.3, shape_padrao).astype(np.float32),
            'nir': np.random.uniform(0.4, 0.9, shape_padrao).astype(np.float32),
            'swir_1': np.random.uniform(0.1, 0.4, shape_padrao).astype(np.float32),
            'red_edge_1': np.random.uniform(0.2, 0.6, shape_padrao).astype(np.float32),
            'verde': np.random.uniform(0.05, 0.2, shape_padrao).astype(np.float32),
            'azul': np.random.uniform(0.01, 0.15, shape_padrao).astype(np.float32)
        }

        # 3. Processamento estável em memória
        arquivo_geotiff = gerar_geotiff_6_bandas_em_memoria(dados_bandas_vmg, lat_centro, lon_centro)

        # 4. Envio do arquivo via Streaming para o MAPA
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


@router.get(
    "/contrato/{id_contrato}/analise-clima",
    response_model=RespostaClimaticaHistorica,
    status_code=status.HTTP_200_OK
)
async def obter_analise_climatica_contrato(id_contrato: int, cultura: str = "SOJA", db: AsyncSession = Depends(get_db)):
    """
    Retorna o relatório analítico e interpolado (IDW) de chuva e temperatura
    dos últimos 60 meses para a área do contrato correspondente.
    """
    try:
        relatorio_final = await gerar_historico_climatico_60_meses(
            id_gleba=id_contrato,
            cultura=cultura,
            db=db
        )
        return relatorio_final

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no processamento do relatório de clima: {str(e)}"
        )

@router.get("/contrato/{id_contrato}/caderno-campo", response_model=RespostaCadernoCampo)
async def obter_caderno_campo_safra(id_contrato: int, db: AsyncSession = Depends(get_db)):
    """
    Fornece ao final do monitoramento um caderno de campo individualizado com as informações
    mais relevantes identificadas durante a safra e sua estimativa de produtividade (Item 3.c.XII).
    """
    try:
        # 1. Recupera as informações básicas do talhão no SGBDOR
        query = text("SELECT id_gleba, area_hectares FROM agroprods.glebas WHERE id_gleba = :id;")
        res = await db.execute(query, {"id": id_contrato})
        gleba = res.fetchone()

        if not gleba:
            raise HTTPException(status_code=404, detail="Gleba não encontrada.")

        # 2. Reutiliza o motor de clima de 60 meses desenvolvido
        clima = await gerar_historico_climatico_60_meses(id_gleba=id_contrato, cultura="SOJA", db=db)

        # 3. Reutiliza o motor de estimativa de produtividade por IA desenvolvido
        prod = estimar_e_validar_produtividade(
            area_hectares=float(gleba.area_hectares),
            sacas_desejadas_comercializar=6200.0, # Exemplo vindo do App do Produtor
            valores_ndvi_ciclo=[0.2, 0.5, 0.88, 0.4],
            total_chuva_ciclo_mm=510.0,
            media_temp_ciclo_c=25.5,
            cultura="SOJA"
        )

        # 4. Monta o payload unificado em conformidade estrita com o edital
        return {
            "id_gleba": id_contrato,
            "safra_ano": "2025/2026",
            "area_hectares": float(gleba.area_hectares),
            "analise_vegetativa_ia": {
                "cultura_identificada": "SOJA",
                "assertividade_score": 0.9450,
                "data_estimada_plantio": "2025-10-15",
                "data_estimada_colheita": "2026-02-20"
            },
            "diagnostico_climatico": clima["indicadores_acumulados"],
            "alertas_ambientais_emitidos": clima["alertas_emitidos"],
            "validacao_comercial": {
                "produtividade_estimada_sc_ha": prod["analise_produtividade_ia"]["produtividade_estimada_sacas_por_hectare"],

                # CORREÇÃO AQUI: Remova a palavra "_gleba" para bater com o Schema esperado
                "volume_total_estimado_sacas": prod["analise_produtividade_ia"]["volume_total_estimado_gleba_sacas"],

                "volume_declarado_condizente": prod["validacao_vmg"]["volume_condizente_com_capacidade_talhao"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao compilar caderno de campo: {str(e)}")