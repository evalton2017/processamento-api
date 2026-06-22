import os
import joblib
import psycopg2
import numpy as np
from xgboost import XGBClassifier
from scipy.interpolate import interp1d
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

# Parâmetros de Conexão com a VPS Agroprodes
USER = 'user_prods'
PASSWORD = 'duke#2214'
HOST = 'vps66374.publiccloud.com.br'
PORT = '5432'
DATABASE = 'agro_prods'

def ajustar_assinatura_fenologica(dados_ndvi, tamanho_alvo=60):
    """
    Interpola linearmente a série temporal real do Sentinel-2.
    Garante que o modelo receba exatamente as 60 features cronológicas exigidas.
    """
    comprimento_atual = len(dados_ndvi)
    if comprimento_atual == tamanho_alvo:
        return dados_ndvi

    # Cria eixos temporais normalizados de 0 a 1
    x_atual = np.linspace(0, 1, comprimento_atual)
    x_alvo = np.linspace(0, 1, tamanho_alvo)

    # Aplica Spline Linear para reconstruir buracos causados por nuvens
    interpolador = interp1d(x_atual, dados_ndvi, kind='linear', fill_value="extrapolate")
    return interpolador(x_alvo).astype(np.float32)

def executar_treinamento_real():
    # 1. Estabelece a conexão com o banco de dados geográfico
    try:
        conn = psycopg2.connect(
            dbname=DATABASE, user=USER, password=PASSWORD, host=HOST, port=PORT, client_encoding="utf8"
        )
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ Erro crítico de conexão com a VPS: {e}")
        return

    # 2. Busca as assinaturas temporais do satélite e o rótulo validado (Ground Truth)
    print("📥 Buscando séries temporais do Sentinel-2 na tabela de treinamento...")
    cursor.execute("""
                   SELECT ndvi, UPPER(TRIM(cultura_real))
                   FROM agroprods.treinamento_culturas
                   WHERE ndvi IS NOT NULL;
                   """)
    registros = cursor.fetchall()

    cursor.close()
    conn.close()

    if len(registros) < 10:
        print(f"⚠️ Base insuficiente para treinamento real: Encontrados apenas {len(registros)} registros.")
        print("Execute o pipeline de análise para coletar e salvar os rasters do Sentinel primeiro.")
        return

    # 3. Mapeamento de classes dinâmico baseado no que existe na base
    culturas_detectadas = sorted(list(set(reg[1] for reg in registros if reg[1])))
    mapeamento_classes = {nome: i for i, nome in enumerate(culturas_detectadas)}
    mapa_reverso_producao = {i: nome for i, nome in enumerate(culturas_detectadas)}

    X_lista = []
    y_lista = []

    # 4. Parsing e Alinhamento Dimensional do JSONB
    print("⚙️ Processando e interpolando curvas fenológicas reais...")
    for ndvi_json, cultura_str in registros:
        if not ndvi_json or len(ndvi_json) < 5:  # Filtra glebas com menos de 5 capturas válidas
            continue

        try:
            # Extrai os valores reais computados via COG Streaming do Sentinel
            valores_media = [float(item["ndvi_mean"]) for item in ndvi_json]
            vetor_ndvi = np.array(valores_media, dtype=np.float32)

            # Ajusta para o formato exato de 60 features
            vetor_60_pontos = ajustar_assinatura_fenologica(vetor_ndvi, tamanho_alvo=60)

            X_lista.append(vetor_60_pontos)
            y_lista.append(mapeamento_classes[cultura_str])
        except (KeyError, TypeError):
            # Ignora payloads malformados ou corrompidos sem derrubar o script
            continue

    X = np.array(X_lista)
    y = np.array(y_lista, dtype=np.int32)

    print(f"✅ Matriz de features estruturada. Shape: X={X.shape} | y={y.shape}")
    print("\n🔄 Classes indexadas dinamicamente para o XGBoost:")
    for nome, idx in mapeamento_classes.items():
        print(f"   ➔ Classificador {idx} = {nome}")

    # 5. Divisão da Base de Dados (Treino 80% / Validação 20%)
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.20, random_state=42, stratify=y)

    # 6. Configuração e Ajuste do XGBClassifier para Dados Reais
    modelo = XGBClassifier(
        n_estimators=150,           # Mais estimadores para capturar ruídos reais do satélite
        max_depth=6,                # Profundidade ideal para assinaturas espectrais complexas
        learning_rate=0.08,         # Taxa de aprendizado suave para evitar overfitting
        subsample=0.85,             # Amostragem de linhas para regularização
        colsample_bytree=0.85,      # Amostragem de features por árvore
        eval_metric="mlogloss",
        random_state=42
    )

    print("\n🏋️ Treinando modelo XGBoost com dados de satélite...")
    modelo.fit(X_train, y_train)

    # 7. Avaliação de Métricas (Critérios de Homologação do MAPA)
    print("\n📊 Avaliando indicadores de acurácia (Validação Cruzada)...")
    predicoes = modelo.predict(X_val)

    # Alinha os nomes para exibir no relatório técnico
    target_names = [mapa_reverso_producao[i] for i in sorted(mapa_reverso_producao.keys())]
    print("\n📝 Relatório de Classificação:")
    print(classification_report(y_val, predicoes, target_names=target_names))

    # 8. Salvamento do Artefato Homologado
    base_dir = os.path.dirname(os.path.abspath(__file__))
    caminho_salvamento = os.path.join(base_dir, "classificador_culturas.pkl")

    artefato_final = {
        "modelo": modelo,
        "mapa_reverso_classes": mapa_reverso_producao
    }

    joblib.dump(artefato_final, caminho_salvamento)
    print(f"💾 SUCESSO: Classificador real gravado em: {caminho_salvamento}\n")

if __name__ == "__main__":
    executar_treinamento_real()
