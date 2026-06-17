import os
import joblib
import numpy as np
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestRegressor

# 1. Mapeia e garante a criação da pasta 'modelos' no local correto
dir_atual = os.path.dirname(os.path.abspath(__file__))
pasta_modelos = os.path.join(dir_atual, "modelos")
os.makedirs(pasta_modelos, exist_ok=True)

print(" -> Estruturando dados em matrizes para inicialização da IA real...")

# Modelo 1: Classificador de Culturas (Entrada: 60 meses de NDVI)
# Simula 100 amostras históricas com valores de NDVI entre 0.1 e 0.8
X_classif = np.random.uniform(0.1, 0.8, (100, 60))
# Classes numéricas alvo correspondentes (0: SOJA, 1: MILHO, 2: ALGODAO, 3: PASTAGEM)
y_classif = np.random.choice([0, 1, 2, 3], size=100)

# Modelo 2: Regressor de Produtividade (Entrada: 60 NDVI + 1 Nitrogênio + 1 Temp + 1 Chuva = 63)
X_prod = np.random.uniform(0.1, 0.8, (100, 63))
# Valores alvo simulados de produtividade (entre 30.0 e 95.0 sacas por hectare)
y_prod = np.random.uniform(30.0, 95.0, 100)

print(" -> Treinando os algoritmos (Ajustando os pesos matemáticos)...")
# Instancia os algoritmos reais solicitados no escopo do projeto
modelo_classificacao = XGBClassifier(n_estimators=5, max_depth=3, random_state=42)
modelo_classificacao.fit(X_classif, y_classif)

modelo_produtividade = RandomForestRegressor(n_estimators=5, max_depth=3, random_state=42)
modelo_produtividade.fit(X_prod, y_prod)

# Define o caminho absoluto final dos arquivos binários pkl
caminho_classificador = os.path.join(pasta_modelos, "classificador_culturas.pkl")
caminho_produtividade = os.path.join(pasta_modelos, "produtividade.pkl")

print(" -> Exportando os arquivos binários (.pkl) via joblib...")
# Salva os modelos de forma serializada no disco
joblib.dump(modelo_classificacao, caminho_classificador)
joblib.dump(modelo_produtividade, caminho_produtividade)

print(f"\n[SUCESSO] Modelos gerados com sucesso na pasta de infraestrutura!")
print(f" -> {caminho_classificador}")
print(f" -> {caminho_produtividade}")
print("\nVocê já pode iniciar ou reiniciar o seu Worker do Celery.")