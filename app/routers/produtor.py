from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.gleba_model import GlebaModel
from app.database.models_ledger import ConsentimentoLgpdLedgerModel
from app.database.session import get_db, get_ledger_db
from app.schemas.gleba import RequisicaoGleba
from app.schemas.response.gleba_response import RespostaGlebas
from typing import List

router = APIRouter(prefix="/api/v1/produtor", tags=["Produtor Rural"])

@router.post("/cadastrar-gleba", status_code=status.HTTP_201_CREATED)
async def cadastrar_gleba_vmg(
        dados: RequisicaoGleba,
        db_principal: AsyncSession = Depends(get_db),
        db_ledger: AsyncSession = Depends(get_ledger_db)
):
    try:
        # Abrimos a transação distribuída em ambas as bases simultaneamente.
        # Qualquer falha a partir daqui aplicará ROLLBACK automático em ambas.
        async with db_principal.begin(), db_ledger.begin():

            # 1. Consulta dos dados do CAR dentro do bloco transacional
            query = text(
                "SELECT num_area, des_condic FROM agroprods.base_car WHERE cod_imovel = :numero_car;"
            )
            res = await db_principal.execute(
                query, {"numero_car": dados.numero_car}
            )
            propriedade = res.fetchone()

            # Validação imediata: se não encontrar, a exceção cancelará a transação
            if not propriedade:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Propriedade não encontrada em bases públicas.",
                )

            # 2. Persistência no banco principal (agroprods) usando o dado recuperado
            data_criacao_convertida = datetime.strptime(
                dados.data_estimada_plantio, "%Y-%m-%d"
            )

            # 2. Persistência no banco principal (agroprods)
            nova_gleba = GlebaModel(
                id_produtor=dados.id_produtor,
                geometria=dados.geometria,
                codigo_car=dados.numero_car,
                cultura_declarada=dados.cultura_declarada,
                data_estimada_plantio=data_criacao_convertida,
                area_hectares=propriedade.num_area,
            )
            db_principal.add(nova_gleba)

            # O flush sincroniza com o banco e gera o id_gleba sem commitar a transação
            await db_principal.flush()

            # 3. Persistência no banco de auditoria (ledger)
            novo_consentimento = ConsentimentoLgpdLedgerModel(
                id_produtor=dados.id_produtor,
                autorizado_cruzamento_car=True,
                ip_origem="192.168.1.50",
                dispositivo_token="token_exemplo_vmg_2026",
            )
            db_ledger.add(novo_consentimento)

            # Sincroniza os dados do ledger antes de encerrar o bloco
            await db_ledger.flush()

        # Fora do bloco 'async with', ambas as bases já realizaram o COMMIT com sucesso.
        return {
            "status": "SUCESSO",
            "mensagem": "Dados persistidos com sucesso nos esquemas correspondentes.",
            "id_gleba_gerado": nova_gleba.id_gleba,
            "area_validada_hectares": propriedade.num_area,
        }

    except HTTPException:
        # Repassa exceções HTTP conhecidas (como o 404 de propriedade não encontrada)
        raise

    except Exception as e:
        # Captura erros inesperados do banco ou de sistema
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na transação distribuída: {str(e)}",
        )

@router.get("/gleba/{id_contrato}", response_model=RespostaGlebas)
async def consultar_gleba(
        id_contrato: int,
        db_principal: AsyncSession = Depends(get_db)
):
    try:
        # Abrimos a transação distribuída em ambas as bases simultaneamente.
        # Qualquer falha a partir daqui aplicará ROLLBACK automático em ambas.
        async with db_principal.begin():

            query = text("""
                         SELECT
                             id_gleba,
                             id_produtor,
                             codigo_car,
                             ST_AsText(geometria) AS geometria,
                             area_hectares,
                             data_criacao,
                             cultura_declarada,
                             data_estimada_plantio
                         FROM agroprods.glebas
                         WHERE id_gleba = :id_contrato;
                         """)
            res = await db_principal.execute(query, {"id_contrato": id_contrato})
            gleba = res.fetchone()

            # Validação imediata: se não encontrar, a exceção cancelará a transação
            if not gleba:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="gleba não encontrada.",
                )

        return {
            "id_gleba": gleba[0],
            "id_produtor": gleba[1],
            "codigo_car": gleba[2],
            "geometria": gleba[3],
            "area_hectares": float(gleba[4]), # Converte Decimal para float
            "data_criacao": gleba[5].date() if hasattr(gleba[5], 'date') else gleba[5],
            "cultura_declarada": gleba[6],
            "data_estimada_plantio": gleba[7].date() if hasattr(gleba[7], 'date') else gleba[7]
        }

    except HTTPException:
        # Repassa exceções HTTP conhecidas (como o 404 de propriedade não encontrada)
        raise

    except Exception as e:
        # Captura erros inesperados do banco ou de sistema
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na transação distribuída: {str(e)}",
        )

@router.get("/{id_produtor}/glebas", response_model=List[RespostaGlebas])
async def consultar_glebas_por_produtor(
        id_produtor: int,
        db_principal: AsyncSession = Depends(get_db)
):
    try:
        async with db_principal.begin():
            # Query alterada para filtrar por id_produtor
            query = text("""
                         SELECT
                             id_gleba,
                             id_produtor,
                             codigo_car,
                             ST_AsText(geometria) AS geometria,
                             area_hectares,
                             data_criacao,
                             cultura_declarada,
                             data_estimada_plantio
                         FROM agroprods.glebas
                         WHERE id_produtor = :id_produtor;
                         """)
            res = await db_principal.execute(query, {"id_produtor": id_produtor})

            # Alterado para fetchall() para trazer todas as linhas do banco
            todas_glebas = res.fetchall()

            # Retorna uma lista vazia caso o produtor não tenha nenhuma gleba cadastrada
            if not todas_glebas:
                return []

        # Monta a lista mapeando cada linha (tupla) retornada do banco
        lista_retorno = []
        for gleba in todas_glebas:
            lista_retorno.append({
                "id_gleba": gleba[0],
                "id_produtor": gleba[1],
                "codigo_car": gleba[2],
                "geometria": gleba[3],
                "area_hectares": float(gleba[4]),
                "data_criacao": gleba[5].date() if hasattr(gleba[5], 'date') else gleba[5],
                "cultura_declarada": gleba[6],
                "data_estimada_plantio": gleba[7].date() if hasattr(gleba[7], 'date') else gleba[7]
            })

        return lista_retorno

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na transação distribuída ao buscar glebas: {str(e)}",
        )

