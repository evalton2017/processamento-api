from typing import List

from fastapi import APIRouter, Query
from fastapi import Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.cache_service import ZarcCacheService
# Importação da sessão unificada criada no passo anterior
from app.database.session import get_async_db
# Importação dos modelos estruturados por schema
from app.dto.RequisicaoGleba import RequisicaoGleba
from app.dto.produtor.panejamento_dto import ZoneamentoZarcResponse, ValidarZarcSimplificadoResponse
from app.dto.response.ClimaResponse import ValidarZarcRequest, CulturaZarcResponse
from app.dto.response.gleba_response import RespostaGlebas, RespostaConsultaGlebasPainel, KpisResumoGlebas, \
    ItemTabelaGleba
from app.dto.response.municipio_response import MunicipioResponse
from app.repository.gleba_repository import GlebaRepository
from app.repository.zarc_repository import ZarcRepository
from app.services.dominio_service import DomínioService
from app.services.gleba_service import GlebaService
from app.services.produtor.produtor_service import ProdutorService
from app.services.validacoes.validacao_zarc_service import ValidacaoZarcService

router = APIRouter(prefix="/api/v1/produtor", tags=["Produtor Rural"])

# ==============================================================================
# NOVO ENDPOINT DE VALIDAÇÃO AGROCLIMÁTICA (ZARC)
# ==============================================================================

def mapear_decendio_para_periodo(decendio: int, ano: int = 2026) -> str:
    meses = [
        "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
        "Jul", "Ago", "Set", "Out", "Nov", "Dez"
    ]
    # Cada mês tem exatamente 3 decêndios
    mes_idx = (decendio - 1) // 3
    sub_decendio = (decendio - 1) % 3

    if sub_decendio == 0:
        return f"01 a 10 de {meses[mes_idx]}"
    elif sub_decendio == 1:
        return f"11 a 20 de {meses[mes_idx]}"
    else:
        # Simplificação de dias finais (28 a 31 dependendo do mês)
        return f"21 a 30/31 de {meses[mes_idx]}"

@router.post("/cadastrar-gleba", status_code=status.HTTP_201_CREATED)
async def cadastrar_gleba_vmg(
        dados: RequisicaoGleba,
        db_principal: AsyncSession = Depends(get_async_db)
):
    service = GlebaService(db_principal)
    return await service.cadastrar_gleba(dados)


@router.get("/gleba/{id_contrato}", response_model=RespostaGlebas)
async def consultar_gleba(
        id_contrato: int,
        db_principal: AsyncSession = Depends(get_async_db)
):
    service = GlebaService(db_principal)
    return await service.obter_gleba(id_contrato)


@router.get("/{id_produtor}/glebas", response_model=List[RespostaGlebas], status_code=status.HTTP_200_OK)
async def consultar_glebas_por_produtor_auditadas(
        id_produtor: int,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Retorna a listagem de geometrias WKT e metadados de conformidade
    extraídos do Ledger imutável do schema audit para renderização no mapa.
    """
    service = GlebaService(db_principal)
    return await service.listar_glebas_por_produtor(id_produtor)

@router.get("/car/{numero_car}", status_code=status.HTTP_200_OK)
async def buscar_detalhes_car(
        numero_car: str,
        db_principal: AsyncSession = Depends(get_async_db)
):
    service = ProdutorService(db_principal)
    return await service.buscar_detalhes_car(numero_car)


@router.get("/municipios", response_model=List[MunicipioResponse])
async def consultar_municipios(
        db_principal: AsyncSession = Depends(get_async_db)
):
    service = ProdutorService(db_principal)
    return await service.listar_municipios()


@router.get("/geocodificar-centroide", status_code=status.HTTP_200_OK)
async def identificar_municipio_por_coordenadas(
        lat: float,
        lon: float,
        db_principal: AsyncSession = Depends(get_async_db)
):
    service = ProdutorService(db_principal)
    return await service.identificar_municipio_por_coordenadas(lat, lon)

class RequisicaoCalcularArea(BaseModel):
    geometria: str  # String WKT 'POLYGON(...)' ou 'MULTIPOLYGON(...)'
@router.post("/calcular-area-geometria", status_code=status.HTTP_200_OK)
async def calcular_area_geometria_postgis(
        dados: RequisicaoCalcularArea,
        db_principal: AsyncSession = Depends(get_async_db)
):
    service = DomínioService(db_principal)
    return await service.calcular_area_geometria(dados.geometria)


@router.get("/culturas", response_model=List[CulturaZarcResponse])
async def obter_culturas_cadastradas_vmg(
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Lista as culturas ativas do ZARC homologadas para a Infraestrutura VMG.
    Busca prioritariamente do cache Redis de inicialização para máxima performance.
    """
    from app.main import redis_client  # Importa o cliente ativo do main
    cache_service = ZarcCacheService(redis_client)

    # 1. Tenta recuperar da memória RAM (O(1))
    culturas = await cache_service.obter_culturas_cache()

    if culturas:
        return culturas  # Retorna imediatamente sem tocar no banco de dados!

    repository = ZarcRepository(db_principal)
    linhas_sql = await repository.listar_culturas(ativo=True, grupo="GRÃOS")

    return [
        {
            "id": row.id, "codigo": row.codigo, "nome": row.nome,
            "grupo": row.grupo, "ativo": row.ativo, "permite_zarc": row.permite_zarc,
            "data_cadastro": row.data_cadastro
        }
        for row in linhas_sql
    ]

# --- Rota de Validação Limpa e Injetada ---
@router.post("/validar-zarc", response_model=ValidarZarcSimplificadoResponse)
async def cadastrar_gleba_vmg(
        payload: ValidarZarcRequest,
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Endpoint de validação que delega a lógica de banco ao Repository e a validação ao Service.
    """
    # Instancia as camadas injetando as dependências de trás para frente
    repository = ZarcRepository(db_principal)
    service = ValidacaoZarcService(repository)

    # Executa a regra isolada extraindo apenas a data pura (.date()) para o serviço
    resultado = await service.validar_planejamento_zarc(payload)

    return ValidarZarcSimplificadoResponse(**resultado)

@router.get("/janela-geral", response_model=ZoneamentoZarcResponse)
async def obter_janela_geral_zarc(
        cultura: str = Query(..., description="Nome da cultura (ex: Feijão)"),
        municipio_ibge: int = Query(..., description="Código IBGE do município"),
        safra: str = Query(..., description="Safra vigente selecionada (ex: 2026/2027)"),  # 🟢 INCLUÍDO
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Consome dinamicamente a tabela oficial de riscos do ZARC (agroprods.zarc_zoneamento)
    para alimentar os cards clicáveis do front-end Angular baseando-se no ano da safra ativa.
    """
    repository = ZarcRepository(db_principal)
    service = ValidacaoZarcService(repository)

    # O service agora recebe a safra para calcular o range correto de datas
    resultado = await service.consultar_janela_geral_zarc(
        municipio_ibge=municipio_ibge,
        cultura=cultura,
        safra=safra  # 🟢 REPASSADO PARA O SERVIÇO
    )

    return resultado

@router.get("/{id_produtor}/consulta-glebas", response_model=RespostaConsultaGlebasPainel, status_code=status.HTTP_200_OK)
async def obter_painel_gerencial_glebas_produtor(
        id_produtor: int,
        safra: str = Query("2026/2027", description="Filtro de safra selecionado na barra superior"),
        db_principal: AsyncSession = Depends(get_async_db)
):
    """
    Retorna a estrutura consolidada para o painel de gerenciamento do produtor rural,
    contendo os contadores estatísticos superiores e a listagem de registros da tabela.
    """
    repo = GlebaRepository(db_principal)
    linhas_banco = await repo.obter_painel_completo_glebas(id_produtor, safra)

    # Contadores reativos locais para alimentar os KPIs superiores
    total_cadastradas = len(linhas_banco)
    total_conformes = 0
    total_em_analise = 0
    total_alertas = 0

    lista_glebas_formatada = []

    for r in linhas_banco:
        # Incrementa os contadores com base no status real deduzido do Ledger
        if r.status == "Conforme":
            total_conformes += 1
        elif r.status == "Em analise":
            total_em_analise += 1
        elif r.status == "Alerta":
            total_alertas += 1

        lista_glebas_formatada.append(
            ItemTabelaGleba(
                id_gleba=r.id_gleba,
                codigo=r.codigo,
                nome_gleba=f"Fazenda {r.cultura_declarada} {r.id_gleba}" if not r.nome_gleba else r.nome_gleba,
                municipio=r.municipio,
                cultura_declarada=r.cultura_declarada if r.cultura_declarada else "Não Informada",
                area_ha=float(r.area_ha),
                status=r.status,
                ultima_atualizacao=r.ultima_atualizacao.strftime("%d/%m/%Y %H:%M") if r.ultima_atualizacao else "",
                geometria=r.geometria
            )
        )

    # Consolida o DTO final simétrico ao layout do dashboard do frontend Angular
    return RespostaConsultaGlebasPainel(
        kpis=KpisResumoGlebas(
            total_cadastradas=total_cadastradas,
            total_conformes=total_conformes,
            total_em_analise=total_em_analise,
            total_alertas=total_alertas,
            proxima_validacao="15/07/2026" # Fixado conforme a agenda de regulação do MAPA
        ),
        glebas=lista_glebas_formatada
    )