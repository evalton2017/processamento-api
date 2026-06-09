import numpy as np
from sklearn.metrics import confusion_matrix, cohen_kappa_score, accuracy_score

def calcular_assertividade_anexo_vi(culturas_reais: list, culturas_preditas: list) -> dict:
    """
    Implementa a metodologia matemática de validação de assertividade do Anexo VI.
    Calcula a Acurácia Global, Índice Kappa e métricas por classe de cultura.
    """
    if len(culturas_reais) != len(culturas_preditas) or len(culturas_reais) == 0:
        raise ValueError("As listas de verdade de campo e predições da IA devem ter o mesmo tamanho e não estarem vazias.")

    # 1. Identifica as classes de culturas presentes no teste semestral
    classes = sorted(list(set(culturas_reais + culturas_preditas)))

    # 2. Gera a Matriz de Confusão Estruturada
    matriz = confusion_matrix(culturas_reais, culturas_preditas, labels=classes)

    # 3. Executa as fórmulas matemáticas exigidas no processo de validação
    acuracia_global = accuracy_score(culturas_reais, culturas_preditas)
    indice_kappa = cohen_kappa_score(culturas_reais, culturas_preditas)

    # 4. Calcula a Assertividade Individual por Cultura (Acurácia do Produtor e do Usuário)
    analise_por_cultura = {}
    for i, cultura in enumerate(classes):
        vp = matriz[i, i]  # Verdadeiros Positivos
        total_real = np.sum(matriz[i, :])  # Total de amostras reais daquela cultura
        total_predito = np.sum(matriz[:, i])  # Total que a IA disse que era aquela cultura

        # Acurácia do Produtor (Sensibilidade / Recall)
        assertividade_inclusao = float(vp / total_real) if total_real > 0 else 0.0
        # Acurácia do Usuário (Precisão)
        assertividade_precisao = float(vp / total_predito) if total_predito > 0 else 0.0

        analise_por_cultura[cultura] = {
            "amostras_reais_campo": int(total_real),
            "assertividade_inclusao_recall": round(assertividade_inclusao, 4),
            "assertividade_precisao_precision": round(assertividade_precisao, 4)
        }

    # 5. Classificação qualitativa do Índice Kappa (Critério de aprovação da Secretaria)
    # Valores acima de 0.80 indicam concordância quase perfeita
    if indice_kappa >= 0.80:
        status_homologacao = "APROVADO_EXCELENTE"
    elif indice_kappa >= 0.61:
        status_homologacao = "APROVADO_BOM"
    else:
        status_homologacao = "REPROVADO_AJUSTE_REQUISITADO"

    return {
        "status_validacao_secretaria": status_homologacao,
        "metricas_globais_anexo_vi": {
            "acuracia_global_overall": round(float(acuracia_global), 4),
            "indice_kappa_score": round(float(indice_kappa), 4)
        },
        "detalhamento_por_cultura": analise_por_cultura,
        "matriz_confusao": {
            "classes_ordenadas": classes,
            "matriz_valores": matriz.tolist()
        }
    }
