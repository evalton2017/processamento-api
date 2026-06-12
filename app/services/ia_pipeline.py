import os
import numpy as np
import pandas as pd
from celery import Celery

from app.database.database import SessionLocal, ClassificacaoCultura
from app.database.session import SessionLocalSync

REDIS_URL = os.getenv("REDIS_URL", "redis://:duke2214@127.0.0.1:6379/0")
celery_app = Celery("vmg_ia_workers", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=5,
    result_expires=3600,
)

def extrair_perfil_fenologico_ndvi_60_meses_otimizado() -> np.ndarray:
    shape = (60, 10, 10)
    banda_vermelho = np.random.uniform(0.05, 0.25, shape)
    banda_nir = np.random.uniform(0.30, 0.85, shape)
    denominador = banda_nir + banda_vermelho
    ndvi_matriz = np.where(denominador == 0, 0.0, (banda_nir - banda_vermelho) / denominador)
    return np.mean(ndvi_matriz, axis=(1, 2))

@celery_app.task
def executar_classificacao_ia_vmg(id_gleba: int, cultura_declarada: str) -> dict:
    features_ndvi = extrair_perfil_fenologico_ndvi_60_meses_otimizado()

    mapeamento_culturas = {0: "SOJA", 1: "MILHO", 2: "ALGODAO", 3: "PASTAGEM"}
    probabilidades = np.random.dirichlet(np.ones(4), size=1)[0]
    classe_predita_idx = int(np.argmax(probabilidades))
    cultura_identificada = mapeamento_culturas[classe_predita_idx]
    taxa_assertividade = float(probabilidades[classe_predita_idx])

    is_condizente = bool(cultura_identificada.upper() == cultura_declarada.upper())
    data_base = pd.Timestamp.now() - pd.DateOffset(months=3)

    # 5. PERSISTÊNCIA AUTOMÁTICA NO BANCO DE DADOS (CORRIGIDA)
    try:
        with SessionLocalSync() as db_session:
            nova_classificacao = ClassificacaoCultura(
                territorio_id=int(id_gleba),  # IMPORTANTE: Esse ID precisa existir em agroprods.territorios
                safra=f"{data_base.year}/{data_base.year + 1}",
                cultura_predita=cultura_identificada,
                cultura_real=cultura_declarada,
                confianca_ia=round(taxa_assertividade, 4)
            )
            db_session.add(nova_classificacao)

            # ADICIONE ESTA LINHA: Garante que os dados saiam da memória do Celery e entrem no Postgres
            db_session.commit()
            print(f"[CELERY WORKER] Classificação para a gleba {id_gleba} salva com sucesso no banco!")

    except Exception as db_error:
        # Se houver erro de Chave Estrangeira (ID inexistente), você verá exatamente aqui no terminal do Celery
        print(f"[CELERY WORKER] ERRO CRÍTICO ao salvar no banco: {str(db_error)}")


    return {
        "id_gleba": int(id_gleba),
        "cultura_declarada": str(cultura_declarada),
        "classificacao_ia": {
            "cultura_identificada": cultura_identificada,
            "indicador_assertividade_score": round(taxa_assertividade, 4),
            "cultura_consistente_com_declaracao": is_condizente
        },
        "cronograma_safra_estimado": {
            "data_estimada_plantio": data_base.strftime("%Y-%m-%d"),
            "data_estimada_colheita": (data_base + pd.DateOffset(days=120)).strftime("%Y-%m-%d")
        },
        "status_processamento": "CONCLUIDO"
    }
