from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from sqlalchemy import select
from app.models.gleba_model import GlebaModel, MunicipioIbge
from app.models.models_ledger import ConsentimentoLgpdLedgerModel
from app.database.session import get_db, get_ledger_db
from sqlalchemy import func

from app.dto.RequisicaoGleba import RequisicaoGleba
from app.dto.response.gleba_response import RespostaGlebas

router = APIRouter(prefix="/api/v1/produtor", tags=["Produtor Rural"])

@router.get("/car/{numero_car}", status_code=status.HTTP_200_OK)
async def buscar_detalhes_car(
        numero_car: str,
        db_principal: AsyncSession = Depends(get_db)
):
    try:
        async with db_principal.begin():
            query = text("""
                         SELECT
                             tipo_feicao,
                             SUM(area_hectares) as total_area,
                             ST_AsText(ST_Union(geom)) as geometria_wkt
                         FROM agroprods.car_feicoes_ambientais
                         WHERE cod_imovel = :numero_car
                         GROUP BY tipo_feicao;
                         """)

            res = await db_principal.execute(query, {"numero_car": numero_car})
            feicoes = res.fetchall()

            if not feicoes:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Código do CAR não localizado na base de feições ambientais."
                )

            # Mapeia as áreas e captura a primeira geometria válida para servir de limite do imóvel
            resumo_ambiental = {}
            geometria_imovel_wkt = None

            for row in feicoes:
                resumo_ambiental[row.tipo_feicao.lower()] = float(row.total_area)
                # Guarda a maior geometria ou a primeira encontrada para desenhar a fazenda no mapa
                if row.geometria_wkt and not geometria_imovel_wkt:
                    geometria_imovel_wkt = row.geometria_wkt

            area_total_car = sum(resumo_ambiental.values())

            return {
                "status": "ATIVO",
                "cod_imovel": numero_car,
                "area_total_declarada_ha": round(area_total_car, 2),
                "geometria": geometria_imovel_wkt, # 🟢 NOVO CAMPO: String WKT 'MULTIPOLYGON(...)' ou 'POLYGON(...)'
                "detalhamento_ambiental": resumo_ambiental
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar consulta de feições ambientais e geográficas: {str(e)}",
        )


@router.post("/cadastrar-gleba", status_code=status.HTTP_201_CREATED)
async def cadastrar_gleba_vmg(
        dados: RequisicaoGleba,
        db_principal: AsyncSession = Depends(get_db),
        db_ledger: AsyncSession = Depends(get_ledger_db)
):
    try:
        async with db_principal.begin(), db_ledger.begin():
            # 1. Consulta dos dados do CAR (Mantenha igual...)
            query = text("SELECT des_condic FROM agroprods.base_car WHERE cod_imovel = :numero_car;")
            res = await db_principal.execute(query, {"numero_car": dados.numero_car})
            propriedade = res.fetchone()

            if not propriedade:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propriedade não encontrada.")

            # 2. Conversão da data (Mantenha igual...)
            data_criacao_convertida = datetime.strptime(dados.data_estimada_plantio, "%Y-%m-%d")

            # 3. Persistência no banco principal (agroprods) com o CAST Espacial do PostGIS
            nova_gleba = GlebaModel(
                id_produtor=dados.id_produtor,
                codigo_car=dados.numero_car,
                cultura_declarada=dados.cultura_declarada,
                data_estimada_plantio=data_criacao_convertida,
                area_hectares=dados.area_hectares,
                codigo_municipio=dados.codigo_municipio,

                # 🟢 CORREÇÃO CRÍTICA: Aplica a função espacial para converter a string WKT em Geometria PostGIS (SRID 4326)
                geometria=func.ST_GeomFromText(dados.geometria, 4326)
            )
            db_principal.add(nova_gleba)

            # O flush sincroniza os estados e gera o id_gleba de forma segura
            await db_principal.flush()

            # 4. Persistência no banco de auditoria (ledger) para compliance LGPD
            novo_consentimento = ConsentimentoLgpdLedgerModel(
                id_produtor=dados.id_produtor,
                autorizado_cruzamento_car=True,
                ip_origem=dados.ip_origem or "127.0.0.1",
                dispositivo_token=dados.dispositivo_token or "token_angular_2026",
            )
            db_ledger.add(novo_consentimento)
            await db_ledger.flush()

        return {
            "status": "SUCESSO",
            "mensagem": "Dados persistidos com sucesso nos esquemas correspondentes.",
            "id_gleba_gerado": nova_gleba.id_gleba,
            "area_validada_hectares": float(nova_gleba.area_hectares),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na transação distribuída: {str(e)}",
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
            # Executa a busca baseada no ID do Produtor Rural
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
            todas_glebas = res.mappings().all() # 🟢 CORREÇÃO: Mapeia as colunas por nome para evitar quebras por índice

            if not todas_glebas:
                return []

        lista_retorno = []
        for g in todas_glebas:
            lista_retorno.append({
                "id_gleba": g["id_gleba"],
                "id_produtor": g["id_produtor"],
                "codigo_car": g["codigo_car"],
                "geometria": g["geometria"],
                "area_hectares": float(g["area_hectares"]),
                "data_criacao": g["data_criacao"].date() if isinstance(g["data_criacao"], datetime) else g["data_criacao"],
                "cultura_declarada": g["cultura_declarada"],
                "data_estimada_plantio": g["data_estimada_plantio"].date() if isinstance(g["data_estimada_plantio"], datetime) else g["data_estimada_plantio"],
                "codigo_municipio": g["codigo_municipio"]
            })

        return lista_retorno

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao compilar listagem de glebas do produtor: {str(e)}",
        )


@router.get("/municipios", status_code=status.HTTP_200_OK)
async def listar_municipios_dropdown(
        db_principal: AsyncSession = Depends(get_db)
):
    try:
        async with db_principal.begin():
            stmt = select(
                MunicipioIbge.codigo_municipio,
                MunicipioIbge.nome_municipio,
                MunicipioIbge.sigla_uf,
                MunicipioIbge.estado
            ).order_by(MunicipioIbge.nome_municipio.asc())

            exec_res = await db_principal.execute(stmt)
            municipios = exec_res.all()

            return [
                {
                    "codigo_municipio": m.codigo_municipio,
                    "nome_municipio": m.nome_municipio,
                    "sigla_uf": m.sigla_uf,
                    "estado": m.estado
                }
                for m in municipios
            ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao recuperar malha municipal do IBGE: {str(e)}"
        )


class RequisicaoCalcularArea(BaseModel):
    geometria: str  # String WKT 'POLYGON(...)' ou 'MULTIPOLYGON(...)'

@router.post("/calcular-area-geometria", status_code=status.HTTP_200_OK)
async def calcular_area_geometria_postgis(
        dados: RequisicaoCalcularArea,
        db_principal: AsyncSession = Depends(get_db)
):
    """
    Usa o PostGIS para calcular com precisão geodésica real a área em hectares
    e o perímetro em metros, mitigando distorções de projeção cartográfica.
    """
    try:
        async with db_principal.begin():
            # 🟢 CORREÇÃO CRÍTICA: Convertendo para ::geography (WGS84) obtemos a área real na superfície da terra.
            # O SRID 3857 distorce áreas no Brasil de forma acentuada, invalidando o compliance do item 3.6-d da portaria.
            query = text("""
                    SELECT 
                        ROUND((ST_Area(ST_GeomFromText(:wkt, 4326)::geography) / 10000)::numeric, 2) as area_ha,
                        ROUND(ST_Perimeter(ST_GeomFromText(:wkt, 4326)::geography)::numeric, 2) as perimetro_m;
                """)

            res = await db_principal.execute(query, {"wkt": dados.geometria})
            resultado = res.fetchone()

            if not resultado or resultado.area_ha is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não foi possível processar a geometria fornecida. Verifique se o formato WKT está íntegro."
                )

            return {
                "area_hectares": float(resultado.area_ha),
                "perimetro_metros": float(resultado.perimetro_m)
            }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no PostGIS ao calcular métricas espaciais: {str(e)}"
        )

@router.get("/geocodificar-centroide", status_code=status.HTTP_200_OK)
async def identificar_municipio_por_coordenadas(
        lat: float,
        lon: float,
        db_principal: AsyncSession = Depends(get_db)
):
    """
    Identifica dinamicamente o município do IBGE correspondente cruzando o ponto
    do centróide através da relação de contenção espacial contida na malha geográfica.
    """
    try:
        async with db_principal.begin():
            # 🟢 CORREÇÃO CRÍTICA: Usa ST_Contains sobre a coluna geométrica real do município (geom).
            # A busca matemática euclidiana falha severamente perto de divisas políticas territoriais.
            query = text("""
                         SELECT
                             codigo_municipio,
                             nome_municipio,
                             sigla_uf,
                             estado
                         FROM agroprods.municipio_ibge
                         WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
                             LIMIT 1;
                         """)

            res = await db_principal.execute(query, {"lat": lat, "lon": lon})
            municipio = res.fetchone()

            # Fallback caso a tabela de municípios do cliente utilize busca por proximidade indexada por coordenadas
            if not municipio:
                query_fallback = text("""
                                      SELECT codigo_municipio, nome_municipio, sigla_uf, estado
                                      FROM agroprods.municipio_ibge
                                      ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) ASC
                                          LIMIT 1;
                                      """)
                res_fallback = await db_principal.execute(query_fallback, {"lat": lat, "lon": lon})
                municipio = res_fallback.fetchone()

            if not municipio:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Nenhum município localizado para o ponto geográfico fornecido."
                )

            return {
                "codigo_municipio": municipio.codigo_municipio,
                "nome_municipio": municipio.nome_municipio,
                "sigla_uf": municipio.sigla_uf,
                "estado": municipio.estado
            }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao geocodificar centróide via PostGIS: {str(e)}"
        )