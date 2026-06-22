import os
import json
import joblib
import psycopg2
import numpy as np
from scipy.interpolate import interp1d
from sklearn.ensemble import RandomForestRegressor

user = 'user_prods'
password = 'duke#2214'
host = 'vps66374.publiccloud.com.br'
port = '5432'
database = 'agro_prods'
schema_name = 'agroprods'
target_table = 'car_feicoes_ambientais'

def ajustar_serie_temporal_ndvi(dados_ndvi, tamanho_alvo=60):
    """ Mantém a mesma interpolação linear fenológica do pipeline """
    comprimento_atual = len(dados_ndvi)
    if comprimento_atual == tamanho_alvo:
        return dados_ndvi
    x_atual = np.linspace(0, 1, comprimento_atual)
    x_alvo = np.linspace(0, 1, tamanho_alvo)
    interpolador = interp1d(x_atual, dados_ndvi, kind='linear', fill_value="extrapolate")
    return interpolador(x_alvo).astype(np.float32)

def treinar_regressor_produtividade():
    # 1. Conexão estável com a VPS do Agroprodes
    try:
        conn = psycopg2.connect(
            dbname=database, user=user, password=password, host=host, port=port, client_encoding="utf8"
        )
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO DE CONEXÃO: {e}")
        return

    cursor = conn.cursor()

    # ⚠️ REQUISITO DE AUDITORIA: Lemos os dados históricos fenológicos
    # Simulando que a produtividade_real (sacas/ha) já foi colhida e auditada
    cursor.execute("SELECT ndvi, gleba_id FROM agroprods.treinamento_culturas;")
    registros = cursor.fetchall()

    if len(registros) < 10:
        print(f"ERRO: Base de dados insuficiente ({len(registros)} registros). Adicione dados antes de treinar.")
        return

    X_lista = []
    y_lista = []

    print("Processando e alinhando as 63 features por registro...")

    for ndvi_json, gleba_id in registros:
        if not ndvi_json:
            continue

        # A. Extrai e interpola os 60 pontos de NDVI
        valores_media = [item["ndvi_mean"] for item in ndvi_json]
        vetor_ndvi = np.array(valores_media, dtype=np.float32)
        ndvi_60 = ajustar_serie_temporal_ndvi(vetor_ndvi, tamanho_alvo=60)

        # B. Simula/Recupera os 3 fatores ambientais complementares exigidos pelo modelo (60 + 3 = 63)
        # Em produção, esses dados vêm do ClimaRepository e do SoloRepository (Nitrogênio)
        nitrogenio_mock = float(np.random.uniform(30.0, 60.0))
        temperatura_mock = float(np.random.uniform(22.0, 28.0))
        chuva_mock = float(np.random.uniform(150.0, 450.0))

        # C. Concatena horizontalmente na ordem estrita esperada pela classe VMGIntelligenceService
        vetor_features_63 = np.hstack([ndvi_60, [nitrogenio_mock, temperatura_mock, chuva_mock]])

        # D. Simula a produtividade real colhida correspondente (Alvo / Target do Regressor)
        # Ex: Soja/Milho produzindo entre 45 e 90 sacas por hectare de acordo com o pico de NDVI e chuva
        pico_ndvi = float(np.max(ndvi_60))
        produtividade_real = (pico_ndvi * 70) + (chuva_mock * 0.03) + np.random.normal(0, 2)
        produtividade_real = max(10.0, produtividade_real) # Evita valores negativos

        X_lista.append(vetor_features_63)
        y_lista.append(produtividade_real)

    X = np.array(X_lista)
    y = np.array(y_lista)

    print(f"Shape final da matriz de treino da Produtividade: X={X.shape} (Esperado: N, 63), y={y.shape}")

    # 2. Configura o RandomForestRegressor com parâmetros estáveis de produção
    modelo_regressao = RandomForestRegressor(
        n_estimators=150,     # Expandido de 5 para 150 árvores para convergência
        max_depth=12,         # Profundidade suficiente para modelar as interações climáticas
        random_state=42,
        n_jobs=-1             # Usa todos os núcleos da máquina para treinar rápido
    )

    print("Treinando o estimador de produtividade RandomForest...")
    modelo_regressao.fit(X, y)

    # 3. Sobrescreve o arquivo .pkl antigo na pasta correspondente
    base_dir = os.path.dirname(os.path.abspath(__file__))
    caminho_salvamento = os.path.join(base_dir, "produtividade.pkl")

    joblib.dump(modelo_regressao, caminho_salvamento)
    print(f"🚀 SUCESSO: Modelo de produtividade de 63 features gravado em: {caminho_salvamento}\n")

if __name__ == "__main__":
    treinar_regressor_produtividade()
