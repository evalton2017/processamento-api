import asyncio
import os

import joblib
import numpy as np
import psycopg2
from fastapi import APIRouter, Depends, HTTPException, status
from scipy.interpolate import interp1d
from sqlalchemy.ext.asyncio import AsyncSession
from xgboost import XGBClassifier

from app.database.session import get_async_db
from app.repository.repositories import SoloRepository
from app.services.pipelineia.treinamento.capturar_historico_real import calcular_ndvi_real
from app.services.pipelineia.vmg_intelligence_service import VMGIntelligenceService


from app.schemas.treinamento_schema import TriggerCapturaRealRequest, TriggerCapturaRealResponse, \
    RetreinoClassificadorResponse

router = APIRouter(prefix="/v1/treinamento", tags=["IA - Treinamento Dinâmico"])

def ajustar_serie_temporal_ndvi(dados_ndvi, tamanho_alvo=60):
    """ Garante que o dado de treino use a mesma interpolação do pipeline """
    comprimento_atual = len(dados_ndvi)
    if comprimento_atual == tamanho_alvo:
        return dados_ndvi
    x_atual = np.linspace(0, 1, comprimento_atual)
    x_alvo = np.linspace(0, 1, tamanho_alvo)
    interpolador = interp1d(x_atual, dados_ndvi, kind='linear', fill_value="extrapolate")
    return interpolador(x_alvo).astype(np.float32)

@router.post(
    "/trigger-captura",
    response_model=TriggerCapturaRealResponse,
    status_code=status.HTTP_201_CREATED
)
async def disparar_captura_historico_real(
        payload: TriggerCapturaRealRequest,
        db_session: AsyncSession = Depends(get_async_db)
):
    """
    Dispara de forma dinâmica a extração de dados históricos do Sentinel-2 (AWS)
    via COG Streaming para popular a tabela de treinamento da IA (Cold Start).
    Em conformidade com a auditoria retroativa de até 60 meses da Portaria SDI/MAPA Nº 739/2025.
    """
    service = VMGIntelligenceService()
    solo_repo = SoloRepository(db_session)
    loop = asyncio.get_running_loop()

    try:
        # 1. Sincroniza os metadados das imagens de satélite do período informado para o banco espacial
        await service.sincronizar_rasters_gleba(
            solo_repo=solo_repo,
            geometria_wkt=payload.geometria_wkt,
            id_gleba=payload.id_gleba,
            data_inicio=payload.data_inicio,
            data_fim=payload.data_fim
        )

        # 2. Recupera do banco os registros de rasters gerados para processamento
        rasters_salvos = await solo_repo.buscar_rasters(
            id_gleba=payload.id_gleba,
            data_inicio=payload.data_inicio,
            data_fim=payload.data_fim
        )

        if not rasters_salvos:
            raise HTTPException(
                status_code=404,
                detail="Nenhuma cena do Sentinel-2 com cobertura de nuvens aceitável foi encontrada para esta janela e geometria."
            )

        # 1. Executa o COG Streaming de forma segura
        ndvi_resultados = await loop.run_in_executor(
            None,
            calcular_ndvi_real,
            rasters_salvos,
            payload.geometria_wkt
        )

        # 🟢 CORREÇÃO: Cláusula de barreira limpa para evitar quebras de tipagem do FastAPI
        if not ndvi_resultados or len(ndvi_resultados) == 0:
            return TriggerCapturaRealResponse(
                status="COMPLETADO_SEM_DADOS",
                gleba_id=int(payload.id_gleba),
                imagens_processadas=0,
                mensagem="O satélite varreu a área, mas todas as imagens estavam cobertas por nuvens."
            )

        # 2. Formata os dados para o formato JSONB do banco de dados
        payload_ndvi_json = [
            {
                "data": str(item["data"]),
                "ndvi_mean": float(item["ndvi_mean"]),
                "ndvi_std": float(item["ndvi_std"])
            }
            for item in ndvi_resultados
        ]

        # 3. Salva os dados na tabela de treinamento da VPS
        await solo_repo.salvar_dados_para_treinamento(
            gleba_id=payload.id_gleba,
            safra=payload.safra,
            ndvi=payload_ndvi_json,
            cultura_real=payload.cultura_real.upper().strip()
        )

        # Confirma a transação no banco
        await db_session.commit()

        # 🟢 RETORNO BLINDADO: Garante a instanciação perfeita do DTO do Pydantic
        return TriggerCapturaRealResponse(
            status="SUCESSO_CAPTURA_VMG",
            gleba_id=int(payload.id_gleba),
            imagens_processadas=int(len(ndvi_resultados)),
            mensagem=f"Assinatura fenológica de {payload.cultura_real} extraída e salva com sucesso!"
        )

    except HTTPException as http_err:
        await db_session.rollback()
        raise http_err
    except Exception as e:
        await db_session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno no processador geográfico do pipeline: {str(e)}"
        )

@router.post(
    "/retreinar-classificador",
    response_model=RetreinoClassificadorResponse,
    status_code=status.HTTP_200_OK
)
async def executar_retreino_ia_real(db_session: AsyncSession = Depends(get_async_db)):
    """
    Recupera as assinaturas temporais reais armazenadas na tabela 'treinamento_culturas',
    aplica a interpolação temporal de 60 pontos e recalibra os pesos do classificador XGBoost.
    Garante a conformidade de evolução do modelo exigida pela Portaria SDI/MAPA Nº 739/2025.
    """
    # Como a biblioteca psycopg2 utiliza driver síncrono, extraímos os dados usando uma conexão direta limpa.
    # Em produção, você pode mapear um SELECT assíncrono via SQLAlchemy se preferir.
    user = 'user_prods'
    password = 'duke#2214'
    host = 'vps66374.publiccloud.com.br'
    port = '5432'
    database = 'agro_prods'
    schema_name = 'agroprods'
    target_table = 'car_feicoes_ambientais'

    try:
        conn = psycopg2.connect(dbname=database, user=user, password=password, host=host, port=port)
        cursor = conn.cursor()
        cursor.execute("SELECT ndvi, UPPER(TRIM(cultura_real)) FROM agroprods.treinamento_culturas WHERE ndvi IS NOT NULL;")
        registros = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Falha de conexão com o PostgreSQL da VPS: {str(err)}")

    if len(registros) < 1:
        raise HTTPException(
            status_code=400,
            detail="Base de dados vazia. Execute o trigger de captura primeiro para popular os registros reais."
        )

    # Coleta as classes de forma dinâmica (Ex: ['SOJA'])
    culturas_unicas = sorted(list(set(r[1] for r in registros if r[1])))
    mapa_para_xgb = {nome: i for i, nome in enumerate(culturas_unicas)}
    mapa_para_producao = {i: nome for i, nome in enumerate(culturas_unicas)}

    X_lista = []
    y_lista = []

    for ndvi_json, cultura_str in registros:
        if not ndvi_json or len(ndvi_json) == 0:
            continue
        try:
            valores_media = [float(item["ndvi_mean"]) for item in ndvi_json]
            vetor_ndvi = np.array(valores_media, dtype=np.float32)

            # Executa a interpolação para preencher lacunas de nuvens e atingir as 60 posições
            vetor_60 = ajustar_serie_temporal_ndvi(vetor_ndvi, tamanho_alvo=60)

            X_lista.append(vetor_60)
            y_lista.append(mapa_para_xgb[cultura_str])
        except Exception:
            continue

    X = np.array(X_lista)
    y = np.array(y_lista, dtype=np.int32)

    # Configuração do XGBoost adaptada para o volume dinâmico atual
    # Se houver apenas uma classe coletada no Cold Start, limitamos o eval_metric para evitar quebras
    metric = "binary:logistic" if len(culturas_unicas) <= 2 else "multi:softprob"

    modelo = XGBClassifier(
        n_estimators=50,
        max_depth=5,
        learning_rate=0.1,
        objective=metric,
        random_state=42
    )

    try:
        # Executa o Fit na CPU da VPS
        modelo.fit(X, y)

        # Determina o path definitivo de salvamento por cima do pkl antigo
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # Sobe os níveis necessários para atingir a pasta física /modelos/
        caminho_pkl = os.path.abspath(os.path.join(base_dir, "..", "services", "pipelineia", "modelos", "classificador_culturas.pkl"))

        # Garante a criação da pasta caso ela mude de lugar
        os.makedirs(os.path.dirname(caminho_pkl), exist_ok=True)

        artefato_final = {
            "modelo": modelo,
            "mapa_reverso_classes": mapa_para_producao
        }

        joblib.dump(artefato_final, caminho_pkl)

        return RetreinoClassificadorResponse(
            status="XGBOOST_RECALIBRADO",
            total_registros_treino=int(X.shape[0]),
            classes_aprendidas=culturas_unicas,
            caminho_modelo=caminho_pkl,
            mensagem="Pesos da rede atualizados com sucesso a partir dos dados do DBeaver."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro durante o fit ou salvamento do artefato .pkl: {str(e)}")