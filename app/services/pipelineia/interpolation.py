import logging
import time
from typing import Dict

import numpy as np
import pandas as pd

# Configuração do Logger para este módulo
logger = logging.getLogger("app.services.interpolation")


def calcular_distancia_haversine(
        lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calcula a distância em quilômetros entre dois pontos geográficos

    utilizando a fórmula de Haversine.
    """
    R = 6371.0  # Raio médio da Terra em km

    # Força a conversão para float nativo para evitar erros de decimal.Decimal no NumPy
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(
        np.radians, [float(lat1), float(lon1), float(lat2), float(lon2)]
    )

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
            np.sin(dlat / 2) ** 2
            + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    )
    c = 2 * np.arcsin(np.sqrt(a))

    return float(R * c)


def selecionar_tres_estacoes_proximas(
        lat_gleba: float, lon_gleba: float, df_estacoes_inmet: pd.DataFrame
) -> pd.DataFrame:
    """Filtra apenas as estações do INMET com status 'OPERANTE'.

    Calcula a distância até o centroide da gleba e seleciona as 3 mais próximas.
    Garante a substituição automática em caso de falha/pane (Critério 3.8.a).
    """
    inicio_timer = time.perf_counter()

    logger.info(
        f"Iniciando triangulação para a Gleba nas coordenadas ({lat_gleba}, {lon_gleba})"
    )

    # Filtrar apenas as bases operantes no momento do processamento
    df_ativas = df_estacoes_inmet[
        df_estacoes_inmet["status"] == "OPERANTE"
        ].copy()
    logger.debug(
        f"Total de estações encontradas no banco: {len(df_estacoes_inmet)} | Operantes: {len(df_ativas)}"
    )

    if len(df_ativas) < 3:
        logger.error(
            "Falha crítica de infraestrutura: Menos de 3 estações operantes registradas."
        )
        raise ValueError(
            "Falha de infraestrutura: Menos de 3 estações operantes no sistema para triangulação."
        )

    # Garantir tipo numérico float para o cálculo do Haversine
    df_ativas["latitude"] = df_ativas["latitude"].astype(float)
    df_ativas["longitude"] = df_ativas["longitude"].astype(float)

    # Calcular distância da gleba para todas as estações disponíveis
    df_ativas["distancia_km"] = df_ativas.apply(
        lambda r: calcular_distancia_haversine(
            lat_gleba, lon_gleba, r["latitude"], r["longitude"]
        ),
        axis=1,
    )

    # Ordenar por proximidade e retornar o top 3 para formar o triângulo de interpolação
    df_top3 = df_ativas.sort_values(by="distancia_km").head(3)

    tempo_total = (time.perf_counter() - inicio_timer) * 1000

    # Log detalhado do resultado da triangulação
    logger.info(
        f"Triangulação concluída com sucesso em {tempo_total:.2f}ms. Estações selecionadas:"
    )
    for _, row in df_top3.iterrows():
        logger.info(
            f"  - Estação [{row['id']}]: Distância {row['distancia_km']:.2f} km | Status: {row['status']}"
        )

    return df_top3


def interpolar_idw(
        lat_gleba: float,
        lon_gleba: float,
        estacoes_trianguladas: pd.DataFrame,
        parametro_clima: str,
        p: int = 2,
) -> float:
    """Executa a interpolação pelo método Inverse Distance Weighting (IDW).

    O peso de cada estação é inversamente proporcional à sua distância elevada à
    potência p.
    """
    valores = estacoes_trianguladas[parametro_clima].astype(float).values
    distancias = estacoes_trianguladas["distancia_km"].astype(float).values

    # Se a gleba estiver exatamente sobre a coordenada da estação (distância zero)
    if 0 in distancias:
        indice_zero = np.where(distancias == 0)[0][0]
        id_estacao = estacoes_trianguladas["id"].iloc[indice_zero]
        logger.debug(
            f"Coordenada da gleba coincide exatamente com a estação {id_estacao}. Retornando valor real direto."
        )
        return float(valores[indice_zero])

    # Cálculo dos pesos baseado no inverso do quadrado da distância
    pesos = 1.0 / (distancias**p)

    # Média ponderada dos valores climáticos
    valor_interpolado = np.sum(pesos * valores) / np.sum(pesos)
    return float(valor_interpolado)

def executar_interpolacao_clima_gleba(
        lat_gleba: float,
        lon_gleba: float,
        df_todas_estacoes_inmet: pd.DataFrame,
        coluna_temperatura: str = "temp_c",
        coluna_chuva: str = "chuva_mm"
) -> Dict[str, float]:
    """
    Função unificadora (Facade) para o pipeline de IA.
    Triangula as 3 estações operantes mais próximas e executa o algoritmo
    IDW para retornar as duas variáveis climáticas prioritárias exigidas na Portaria.
    """
    try:
        # 1. Executa a triangulação dinâmica isolando as 3 bases operantes mais próximas
        df_triangulado = selecionar_tres_estacoes_proximas(
            lat_gleba=lat_gleba,
            lon_gleba=lon_gleba,
            df_estacoes_inmet=df_todas_estacoes_inmet
        )

        # 2. Executa a interpolação IDW para Temperatura
        temperatura_final = interpolar_idw(
            lat_gleba=lat_gleba,
            lon_gleba=lon_gleba,
            estacoes_trianguladas=df_triangulado,
            parametro_clima=coluna_temperatura
        )

        # 3. Executa a interpolação IDW para Chuva
        chuva_final = interpolar_idw(
            lat_gleba=lat_gleba,
            lon_gleba=lon_gleba,
            estacoes_trianguladas=df_triangulado,
            parametro_clima=coluna_chuva
        )

        return {
            "temperatura": round(temperatura_final, 2),
            "chuva": round(chuva_final, 2)
        }

    except Exception as e:
        logger.error(f"Erro ao processar interpolação IDW para a gleba: {str(e)}", exc_info=True)
        raise e