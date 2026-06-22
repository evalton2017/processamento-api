import os
import json
import joblib
import psycopg2
import numpy as np
from xgboost import XGBClassifier
from scipy.interpolate import interp1d

user = 'user_prods'
password = 'duke#2214'
host = 'vps66374.publiccloud.com.br'
port = '5432'
database = 'agro_prods'
schema_name = 'agroprods'
target_table = 'car_feicoes_ambientais'

def ajustar_serie_temporal_ndvi(dados_ndvi, tamanho_alvo=60):
    """ Garante que o dado de treino use a mesma interpolação do pipeline """
    comprimento_atual = len(dados_ndvi)
    if comprimento_atual == tamanho_alvo:
        return dados_ndvi
    x_atual = np.linspace(0, 1, comprimento_atual)
    x_alvo = np.linspace(0, 1, tamanho_alvo)
    interpolador = interp1d(x_atual, dados_ndvi, kind='linear', fill_value="extrapolate")
    return interpolador(x_alvo).astype(np.float32)

def treinar_classificador():
    # 1. Conexão estável com o banco para buscar o Ground Truth
    try:
        conn = psycopg2.connect(
            dbname=database,
            user=user,
            password=password,
            host=host,
            port=port,
            client_encoding="utf8"
        )
    except Exception as e:
        print("\n❌ ERRO CRÍTICO DE CONEXÃO COM O POSTGRESQL:")
        erro_limpo = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        print(erro_limpo)
        return

    cursor = conn.cursor()
    cursor.execute("SELECT ndvi, UPPER(cultura_real) FROM agroprods.treinamento_culturas;")
    registros = cursor.fetchall()

    if len(registros) < 10:
        print(f"ERRO: Você só tem {len(registros)} registros na tabela. Alimente o banco antes de treinar!")
        return

    # --- MAPEAMENTO DINÂMICO BASEADO NOS DADOS REAIS DO BANCO ---
    # Captura todas as strings de cultura exclusivas presentes no banco de dados
    culturas_unicas_banco = sorted(list(set(reg[1] for reg in registros if reg[1])))

    # Cria o dicionário de treino dinâmico (Ex: {"SOJA": 0, "MILHO": 1, "FEIJAO": 2})
    mapeamento_culturas = {nome_cultura: i for i, nome_cultura in enumerate(culturas_unicas_banco)}
    # Cria o dicionário reverso para a API de produção ler strings direto (Ex: {0: "SOJA", 1: "MILHO"})
    mapa_para_producao = {i: nome_cultura for i, nome_cultura in enumerate(culturas_unicas_banco)}

    X_lista = []
    y_lista = []

    # 2. Processa cada linha do banco convertendo o JSONB para o vetor de 60 posições
    for ndvi_json, cultura_str in registros:
        if not ndvi_json or not cultura_str or cultura_str not in mapeamento_culturas:
            continue

        valores_media = [item["ndvi_mean"] for item in ndvi_json]
        vetor_ndvi = np.array(valores_media, dtype=np.float32)

        # Aplica a interpolação fenológica de 60 pontos
        vetor_ajustado = ajustar_serie_temporal_ndvi(vetor_ndvi, tamanho_alvo=60)

        X_lista.append(vetor_ajustado)
        y_lista.append(mapeamento_culturas[cultura_str])

    X = np.array(X_lista)
    y = np.array(y_lista, dtype=np.int32)

    print(f"Shape dos dados carregados para treino: X={X.shape}, y={y.shape}")

    print("\n🔄 Alinhamento Dinâmico de Classes Concluído para o XGBoost:")
    for nome_cultura, id_interno in mapeamento_culturas.items():
        print(f"   🌾 String do Banco: {nome_cultura} ➔ Categoria Gerada para o XGBoost: {id_interno}")
    print("")

    # 3. Configura o XGBoost com parâmetros de produção
    modelo = XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        eval_metric="mlogloss",
        random_state=42
    )

    # 4. Treina o modelo com o vetor y sequencial automatizado
    print("Treinando o classificador XGBoost Dinâmico...")
    modelo.fit(X, y)

    # 5. Salva o pipeline contendo o classificador e o mapa de classes strings nativas
    base_dir = os.path.dirname(os.path.abspath(__file__))
    caminho_salvamento = os.path.join(base_dir, "classificador_culturas.pkl")

    # Armazena o mapa_reverso contendo as STRINGS direto (elimina dicionário estático no serviço)
    artefato_final = {
        "modelo": modelo,
        "mapa_reverso_classes": mapa_para_producao
    }

    joblib.dump(artefato_final, caminho_salvamento)
    print(f"🚀 SUCESSO: Modelo dinâmico e metadados de strings gravados em: {caminho_salvamento}\n")

if __name__ == "__main__":
    treinar_classificador()
