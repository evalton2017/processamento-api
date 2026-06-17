from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

# Importação da sessão unificada criada no passo anterior
from app.database.session import get_async_db
from app.dto.municipio_response import MunicipioResponse

# Importação dos modelos estruturados por schema
from app.models.gleba_model import GlebaModel, MunicipioIbge
from app.models.models import Pessoa
from app.models.models_ledger import ConsentimentoLgpdLedger

from app.dto.RequisicaoGleba import RequisicaoGleba
from app.dto.response.gleba_response import RespostaGlebas

from app.services.celery.celery_task import executar_pipeline, broker

router = APIRouter(prefix="/api/v1/produtor", tags=["Produtor Rural"])

@router.get("/car/{numero_car}", status_code=status.HTTP_200_OK)
async def buscar_detalhes_car(
        numero_car: str,
        db_principal: AsyncSession = Depends(get_async_db)
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

            resumo_ambiental = {}
            geometria_imovel_wkt = None

            for row in feicoes:
                resumo_ambiental[row.tipo_feicao.lower()] = float(row.total_area)
                if row.geometria_wkt and not geometria_imovel_wkt:
                    geometria_imovel_wkt = row.geometria_wkt

            area_total_car = sum(resumo_ambiental.values())

            return {
                "status": "ATIVO",
                "cod_imovel": numero_car,
                "area_total_declarada_ha": round(area_total_car, 2),
                "geometria": geometria_imovel_wkt,
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
        db_principal: AsyncSession = Depends(get_async_db)
):
    try:
        async with db_principal.begin():
            # =================================================================
            # 1. ATUALIZAÇÃO DA PESSOA (PRODUTOR) VIA CPF
            # =================================================================
            # Realiza a busca da pessoa associada ao id_produtor recebido nos dados
            stmt_pessoa = (
                select(Pessoa)
                .where(Pessoa.id == dados.id_produtor)
            )
            result_pessoa = await db_principal.execute(stmt_pessoa)
            pessoa = result_pessoa.scalar_one_or_none()

            if not pessoa:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Produtor (Pessoa) não encontrado no sistema."
                )

            # Atualiza o campo cpf_cnpj com o dado vindo da requisição
            # Nota: Certifique-se de que 'cpf' existe no esquema do seu 'RequisicaoGleba'
            pessoa.cpf_cnpj = dados.cpf

            # =================================================================
            # 2. CONSULTA DOS DADOS DO CAR
            # =================================================================
            query = text("SELECT id FROM agroprods.car_feicoes_ambientais WHERE cod_imovel = :numero_car;")
            res = await db_principal.execute(query, {"numero_car": dados.numero_car})
            propriedade = res.fetchone()

            if not propriedade:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propriedade não encontrada.")

            # 3. Conversão da data
            data_criacao_convertida = datetime.strptime(dados.data_estimada_plantio, "%Y-%m-%d")

            # 4. Persistência no banco principal (schema: agroprods)
            nova_gleba = GlebaModel(
                id_produtor=dados.id_produtor,
                codigo_car=dados.numero_car,
                cultura_declarada=dados.cultura_declarada,
                data_estimada_plantio=data_criacao_convertida,
                area_hectares=dados.area_hectares,
                codigo_municipio=dados.codigo_municipio,
                geometria=func.ST_GeomFromText(dados.geometria, 4326)
            )
            db_principal.add(nova_gleba)

            # O flush sincroniza os estados e gera o id_gleba de forma segura antes do commit
            await db_principal.flush()

            # 5. Persistência no schema audit usando a mesma sessão do db_principal
            novo_consentimento = ConsentimentoLgpdLedger(
                id_produtor=dados.id_produtor,
                autorizado_cruzamento_car=True,
                ip_origem=dados.ip_origem or "127.0.0.1",
                dispositivo_token=dados.dispositivo_token or "token_angular_2026",
                hash_registro=f"init_hash_{nova_gleba.id_gleba}"  # Inicializador de hash do bloco
            )
            db_principal.add(novo_consentimento)
            await db_principal.flush()

            # 6. Disparo do pipeline assíncrono via Taskiq (kiq)
            await executar_pipeline.kiq(
                id_gleba=nova_gleba.id_gleba,
                cultura_declarada=dados.cultura_declarada,
                id_produtor=dados.id_produtor
            )

        return {
            "status": "SUCESSO",
            "mensagem": "Dados persistidos e cadastro do produtor atualizado com sucesso de forma atômica.",
            "id_gleba_gerado": nova_gleba.id_gleba,
            "area_validada_hectares": float(nova_gleba.area_hectares),
            "produtor_atualizado": pessoa.nome
        }

    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao processar a operação atômica: {str(e)}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na transação atômica multischema: {str(e)}",
        )


@router.get("/gleba/{id_contrato}", response_model=RespostaGlebas)
async def consultar_gleba(
        id_contrato: int,
        db_principal: AsyncSession = Depends(get_async_db)
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
        db_principal: AsyncSession = Depends(get_async_db)
):
    try:
        # 🟢 CONCLUSÃO: Finalização da rota que estava truncada no prompt original
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
            linhas = res.fetchall()

            resultado = []
            for gleba in linhas:
                resultado.append({
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

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao recuperar a lista de glebas do produtor: {str(e)}",
        )
@router.get("/municipios", response_model=List[MunicipioResponse])
async def consultar_municipios(
        db_principal: AsyncSession = Depends(get_async_db)
):
    try:
        async with db_principal.begin():
            # Query selecionando apenas os campos mapeados na interface TypeScript
            query = text("""
                         SELECT
                             codigo_municipio,
                             nome_municipio,
                             sigla_uf,
                             estado
                         FROM agroprods.municipio_ibge;
                         """)

            res = await db_principal.execute(query)
            linhas = res.fetchall()

            resultado = []
            for municipio in linhas:
                resultado.append({
                    "codigo_municipio": municipio[0],
                    "nome_municipio": municipio[1],
                    "sigla_uf": municipio[2],
                    "estado": municipio[3]
                })

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao recuperar a lista de municípios: {str(e)}",
        )

@router.get("/geocodificar-centroide", status_code=status.HTTP_200_OK)
async def identificar_municipio_por_coordenadas(
        lat: float,
        lon: float,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Identifica dinamicamente o município do IBGE correspondente calculando a menor
    distância entre o ponto fornecido e as coordenadas numéricas (lat/lon) armazenadas.
    """
    try:
        async with db_principal.begin():
            # Como a tabela armazena latitude e longitude como colunas numéricas,
            # montamos os pontos espaciais em tempo de execução para calcular a distância física real.
            query = text("""
                         SELECT
                             codigo_municipio,
                             nome_municipio,
                             sigla_uf,
                             estado
                         FROM agroprods.municipio_ibge
                         ORDER BY
                             ST_MakePoint(longitude, latitude)::geography <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography ASC
                         LIMIT 1;
                         """)

            res = await db_principal.execute(query, {"lat": lat, "lon": lon})
            municipio = res.fetchone()

            if not municipio:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Nenhum município localizado no banco de dados."
                )

            return {
                "codigo_municipio": municipio.codigo_municipio,
                "nome_municipio": municipio.nome_municipio,
                "sigla_uf": municipio.sigla_uf,
                "estado": municipio.estado
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao geocodificar centróide via coordenadas numéricas: {str(e)}"
        )

class RequisicaoCalcularArea(BaseModel):
    geometria: str  # String WKT 'POLYGON(...)' ou 'MULTIPOLYGON(...)'
@router.post("/calcular-area-geometria", status_code=status.HTTP_200_OK)
async def calcular_area_geometria_postgis(
        dados: RequisicaoCalcularArea,
        db_principal: AsyncSession = Depends(get_async_db)
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

@router.get("/culturas", status_code=status.HTTP_200_OK)
async def listar_dominio_culturas(
        grupo: Optional[str] = None,
        ativo: Optional[bool] = True,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Retorna a listagem do domínio de culturas cadastradas no sistema,
    permitindo filtros opcionais por grupo e status de ativação.
    """
    try:
        async with db_principal.begin():
            # Construção dinâmica da cláusula WHERE para filtros opcionais
            condicoes = []
            parametros = {}

            if ativo is not None:
                condicoes.append("ativo = :ativo")
                parametros["ativo"] = ativo

            if grupo:
                condicoes.append("grupo = :grupo")
                parametros["grupo"] = grupo

            clausula_where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

            query = text(f"""
                SELECT 
                    id, 
                    codigo, 
                    nome, 
                    grupo, 
                    ativo, 
                    permite_zarc, 
                    data_cadastro
                FROM dominio_culturas
                {clausula_where}
                ORDER BY nome ASC;
            """)

            res = await db_principal.execute(query, parametros)
            culturas = res.fetchall()

            if not culturas:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Nenhuma cultura localizada para os critérios fornecidos."
                )

            return [
                {
                    "id": c.id,
                    "codigo": c.codigo,
                    "nome": c.nome,
                    "grupo": c.grupo,
                    "ativo": c.ativo,
                    "permite_zarc": c.permite_zarc,
                    "data_cadastro": c.data_cadastro.isoformat() if c.data_cadastro else None
                }
                for c in culturas
            ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao consultar o domínio de culturas: {str(e)}"
        )