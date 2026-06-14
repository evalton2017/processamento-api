from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.models.gleba_model import GlebaModel
from app.models.models_ledger import ConsentimentoLgpdLedgerModel
from app.database.session import get_db, get_ledger_db

# Importações dos DTOs que o front-end Angular vai consumir
from app.dto.RequisicaoGleba import RequisicaoGleba
from app.dto.response.gleba_response import RespostaGlebas

router = APIRouter(prefix="/api/v1/produtor", tags=["Produtor Rural"])


@router.post("/cadastrar-gleba", status_code=status.HTTP_201_CREATED)
async def cadastrar_gleba_vmg(
        dados: RequisicaoGleba,
        db_principal: AsyncSession = Depends(get_db),
        db_ledger: AsyncSession = Depends(get_ledger_db)
):
    try:
        # Abrimos a transação distribuída em ambas as bases simultaneamente (Atomicidade ACID)
        async with db_principal.begin(), db_ledger.begin():

            # 1. Validação na base_car (Valida a existência jurídica do imóvel rural)
            query_car = text(
                "SELECT des_condic FROM agroprods.base_car WHERE cod_imovel = :numero_car;"
            )
            res_car = await db_principal.execute(
                query_car, {"numero_car": dados.numero_car}
            )
            propriedade = res_car.fetchone()

            if not propriedade:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Imóvel Rural (CAR) não encontrado nas bases públicas regulatórias.",
                )

            # 2. Conversão segura de datas vindas do formulário do Angular
            try:
                data_plantio_convertida = datetime.strptime(dados.data_estimada_plantio, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Formato de data inválido para data_estimada_plantio. Use o padrão YYYY-MM-DD."
                )

            # 3. Persistência no Banco Principal (agroprods) incluindo os inputs do protótipo
            # Nota: Usamos os novos campos coletados nas etapas do Wizard
            nova_gleba = GlebaModel(
                id_produtor=dados.id_produtor,
                codigo_car=dados.numero_car,
                cultura_declarada=dados.cultura_declarada,
                data_estimada_plantio=data_plantio_convertida,
                # A área agora vem do cálculo poligonal do mapa do front-end (Etapa 3)
                area_hectares=dados.area_hectares,
                # Novo campo mapeado para a relação regional (Etapa 2)
                codigo_municipio=dados.codigo_municipio,
                # Armazenamos a string WKT limpa; o banco converterá espacialmente
                geometria=dados.geometria
            )
            db_principal.add(nova_gleba)

            # O flush sincroniza o estado e gera o 'id_gleba' sequencial sem commitar definitivamente
            await db_principal.flush()

            # 4. Gravação imutável no Ledger (Auditoria e Compliance LGPD)
            # Salvamos os metadados gerados pelo dispositivo do produtor ao assinar o termo
            novo_consentimento = ConsentimentoLgpdLedgerModel(
                id_produtor=dados.id_produtor,
                autorizado_cruzamento_car=True,
                ip_origem=dados.ip_origem or "127.0.0.1",
                dispositivo_token=dados.dispositivo_token or "token_angular_ssr_2026",
            )
            db_ledger.add(novo_consentimento)

            # Sincroniza os dados do ledger antes do fechamento do bloco gerenciado
            await db_ledger.flush()

        # Ao sair do bloco 'async with', o commit distribuído foi executado com sucesso em ambos os bancos.
        return {
            "status": "SUCESSO",
            "mensagem": "Gleba e termo de consentimento gravados com sucesso.",
            "id_gleba_gerado": nova_gleba.id_gleba,
            "area_validada_hectares": float(nova_gleba.area_hectares),
            "status_monitoramento": "Em Validação" # String fixa exigida na última tela do protótipo
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha crítica na transação distribuída de cadastro: {str(e)}",
        )

# =====================================================================
# ROTAS DE CONSULTA (MANTIDAS E REFINADAS COM SUPORTE AO SCHEMA)
# =====================================================================

@router.get("/gleba/{id_contrato}", response_model=RespostaGlebas)
async def consultar_gleba(
        id_contrato: int,
        db_principal: AsyncSession = Depends(get_db)
):
    try:
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
                             data_estimada_plantio,
                             codigo_municipio
                         FROM agroprods.glebas
                         WHERE id_gleba = :id_contrato;
                         """)
            res = await db_principal.execute(query, {"id_contrato": id_contrato})
            gleba = res.fetchone()

            if not gleba:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Gleba agrícola não encontrada no sistema.",
                )

        return {
            "id_gleba": gleba[0],
            "id_produtor": gleba[1],
            "codigo_car": gleba[2],
            "geometria": gleba[3],
            "area_hectares": float(gleba[4]),
            "data_criacao": gleba[5].date() if hasattr(gleba[5], 'date') else gleba[5],
            "cultura_declarada": gleba[6],
            "data_estimada_plantio": gleba[7].date() if hasattr(gleba[7], 'date') else gleba[7],
            "codigo_municipio": gleba[8]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao recuperar dados da gleba: {str(e)}",
        )


@router.get("/{id_produtor}/glebas", response_model=List[RespostaGlebas])
async def consultar_glebas_por_produtor(
        id_produtor: int,
        db_principal: AsyncSession = Depends(get_db)
):
    try:
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
                             data_estimada_plantio,
                             codigo_municipio
                         FROM agroprods.glebas
                         WHERE id_produtor = :id_produtor;
                         """)
            res = await db_principal.execute(query, {"id_produtor": id_produtor})
            todas_glebas = res.fetchall()

            if not todas_glebas:
                return []

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
                "data_estimada_plantio": gleba[7].date() if hasattr(gleba[7], 'date') else gleba[7],
                "codigo_municipio": gleba[8]
            })

        return lista_retorno

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao compilar listagem de glebas do produtor: {str(e)}",
        )
