import os
import joblib
import numpy as np
import logging
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error

logger = logging.getLogger(__name__)

# Mapeia e garante a criação da pasta 'modelos'
dir_atual = os.path.dirname(os.path.abspath(__file__))
pasta_modelos = os.path.join(dir_atual, "modelos")
os.makedirs(pasta_modelos, exist_ok=True)

def executar_esteira_retreinamento(dados_classificacao: tuple = None, dados_produtividade: tuple = None):
    """
    Orquestra o treinamento real, separando dados de teste para validação
    dos indicadores de assertividade conforme Item 3.1 da Portaria.
    """
    print("\n[VFM IA] Iniciando Ciclo Semestral de Calibração de Modelos...")

    # 1. CARREGAMENTO DOS DADOS (Se não vier real do banco, mantém o fallback controlado)
    if dados_classificacao:
        X_c, y_c = dados_classificacao
    else:
        logger.warning("Utilizando dados de simulação para Classificação (Fallback).")
        X_c = np.random.uniform(0.1, 0.8, (200, 60))
        y_c = np.random.choice([0, 1, 2, 3], size=200)

    if dados_produtividade:
        X_p, y_p = dados_produtividade
    else:
        logger.warning("Utilizando dados de simulação para Produtividade (Fallback).")
        X_p = np.random.uniform(0.1, 0.8, (200, 63))
        y_p = np.random.uniform(30.0, 95.0, 200)

    # ==========================================================================
    # 2. SEGREGAÇÃO DE TESTE/TREINO (Essencial para auditoria da Portaria)
    # ==========================================================================
    X_c_train, X_c_test, y_c_train, y_c_test = train_test_split(X_c, y_c, test_size=0.2, random_state=42)
    X_p_train, X_p_test, y_p_train, y_p_test = train_test_split(X_p, y_p, test_size=0.2, random_state=42)

    # 3. AJUSTE DOS PESOS (Treinamento)
    print(" -> Ajustando hiperparâmetros e pesos matemáticos via XGBoost e Random Forest...")

    # Configurações robustas para produção
    modelo_classif = XGBClassifier(n_estimators=50, max_depth=5, learning_rate=0.1, random_state=42)
    modelo_classif.fit(X_c_train, y_c_train)

    modelo_prod = RandomForestRegressor(n_estimators=50, max_depth=6, random_state=42)
    modelo_prod.fit(X_p_train, y_p_train)

    # ==========================================================================
    # 4. VALIDAÇÃO DOS INDICADORES DE ASSERTIVIDADE (Exigência do Item 3.1)
    # ==========================================================================
    preds_c = modelo_classif.predict(X_c_test)
    acuracia_final = accuracy_score(y_c_test, preds_c)

    preds_p = modelo_prod.predict(X_p_test)
    erro_medio = mean_absolute_error(y_p_test, preds_p)

    print("\n==================================================================")
    print("📋 RELATÓRIO DE ASSERTIVIDADE SEMESTRAL (ANEXO VI - PORTARIA)")
    print("==================================================================")
    print(f"✅ Acurácia de Classificação de Culturas (IA): {acuracia_final * 100:.2f}%")
    print(f"📉 Erro Médio Absoluto (MAE) de Produtividade: {erro_medio:.2f} sacas/ha")
    print("==================================================================\n")

    # 5. EXPORTAÇÃO DOS ARQUIVOS BINÁRIOS (.PKL)
    caminho_classificador = os.path.join(pasta_modelos, "classificador_culturas.pkl")
    caminho_produtividade = os.path.join(pasta_modelos, "produtividade.pkl")

    joblib.dump(modelo_classif, caminho_classificador)
    joblib.dump(modelo_prod, caminho_produtividade)

    print(f"[SUCESSO] Modelos imutáveis exportados para a infraestrutura:")
    print(f" -> {caminho_classificador}")
    print(f" -> {caminho_produtividade}")

    return {
        "acuracia_classificacao": float(acuracia_final),
        "mae_produtividade": float(erro_medio)
    }

if __name__ == "__main__":
    # Execução direta via terminal do desenvolvedor ou worker cron semestral
    executar_esteira_retreinamento()
