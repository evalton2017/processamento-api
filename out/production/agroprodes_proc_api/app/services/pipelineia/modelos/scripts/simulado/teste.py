import os
import joblib

# 1. Garante o caminho absoluto correto até o arquivo físico
base_dir = os.path.dirname(os.path.abspath(__file__))
caminho_modelo = os.path.join(base_dir, "produtividade.pkl")

print(f"Tentando carregar o modelo em: {caminho_modelo}")

try:
    # 2. Usa obrigatoriamente o joblib por causa da compressão do RandomForest
    modelo = joblib.load(caminho_modelo)
    print("\n✅ SUCESSO: Modelo de produtividade carregado corretamente!")
    print(modelo)
except Exception as e:
    print(f"\n❌ Erro ao carregar o arquivo: {e}")
    print("Verifique se o nome do arquivo na pasta não está como 'produtividade.pkl.pkl'")
