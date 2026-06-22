import json
import random
import psycopg2
import numpy as np
from datetime import datetime, timedelta

user = 'user_prods'
password = 'duke#2214'
host = 'vps66374.publiccloud.com.br'
port = '5432'
database = 'agro_prods'
schema_name = 'agroprods'
target_table = 'car_feicoes_ambientais'


def conectar_banco():
    # ⚠️ AJUSTE AS CREDENCIAIS DE ACORDO COM O SEU AMBIENTE LOCAL/DOCKER
    return psycopg2.connect(
        host=host,
        database=database,
        user=user,
        password=password,
        port=port
    )

def gerar_curva_fenologica(cultura, total_pontos=45):
    """
    Gera uma série temporal simulando o ciclo real de crescimento da planta.
    Cada ponto representa a média de NDVI capturada pelo satélite no tempo.
    """
    x = np.linspace(0, np.pi, total_pontos)

    if cultura == "SOJA":
        # Ciclo rápido: sobe muito no meio e cai drasticamente na colheita
        y = 0.2 + 0.65 * np.sin(x)**2
    elif cultura == "MILHO":
        # Ciclo rápido: pico ligeiramente deslocado e formato mais pontudo
        y = 0.25 + 0.60 * np.sin(x)**1.5
    elif cultura == "CAFE":
        # Cultura Perene: Mantém folhagem alta e constante o ano todo
        y = 0.65 + 0.10 * np.sin(x)
    else:  # PASTAGEM
        # Linha quase reta com pequenos ruídos de pastejo/seca
        y = 0.45 + 0.05 * np.sin(x * 2)

    # Injeta um ruído randômico leve para simular variações de clima/nuvem reais
    ruido = np.random.normal(0, 0.03, total_pontos)
    y = np.clip(y + ruido, 0.0, 1.0)

    # Monta a estrutura JSONB exigida pela sua tabela
    data_base = datetime(2025, 10, 1)
    registros_ndvi = []

    for i, valor_ndvi in enumerate(y):
        data_corrente = data_base + timedelta(days=i * 5)
        registros_ndvi.append({
            "data": data_corrente.strftime("%Y-%m-%d"),
            "ndvi_mean": float(round(valor_ndvi, 4)),
            "ndvi_std": float(round(random.uniform(0.02, 0.07), 4))
        })

    return registros_ndvi

def popular_tabela_treino():
    conn = conectar_banco()
    cursor = conn.cursor()

    culturas = ["SOJA", "MILHO", "CAFE", "PASTAGEM"]
    safra = "2025/2026"
    total_por_cultura = 40  # 40 glebas de cada = 160 registros para o XGBoost aprender bem

    print(f"Iniciando a carga de dados simulados na safra {safra}...")

    contador = 0
    id_gleba_base = 1000

    for cultura in culturas:
        for _ in range(total_por_cultura):
            id_gleba_base += 1

            # Gera um tamanho de pontos levemente diferente para testar a sua interpolação linear
            tamanho_variado = random.randint(35, 55)
            historico_ndvi = gerar_curva_fenologica(cultura, total_pontos=tamanho_variado)

            try:
                # Alinha com a estrutura exata da sua tabela
                cursor.execute(
                    """
                    INSERT INTO agroprods.treinamento_culturas (gleba_id, safra, ndvi, evi, savi, cultura_real)
                    VALUES (%s, %s, %s, NULL, NULL, %s)
                        ON CONFLICT (gleba_id, safra) DO NOTHING;
                    """,
                    (id_gleba_base, safra, json.dumps(historico_ndvi), cultura)
                )
                contador += 1
            except Exception as e:
                print(f"Erro ao inserir registro para a cultura {cultura}: {e}")
                conn.rollback()
                return

    conn.commit()
    cursor.close()
    conn.close()
    print(f"🚀 SUCESSO: {contador} registros de treinamento agrícolas injetados com sucesso!")

if __name__ == "__main__":
    popular_tabela_treino()