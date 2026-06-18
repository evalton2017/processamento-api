from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

# Importação da sessão unificada criada no passo anterior
from app.database.session import get_async_db
from app.dto.municipio_response import MunicipioResponse

# Importação dos modelos estruturados por schema

from app.dto.RequisicaoGleba import RequisicaoGleba
from app.dto.response.gleba_response import RespostaGlebas

from app.services.dominio_service import DomínioService
from app.services.gleba_service import GlebaService
from app.services.produtor.produtor_service import ProdutorService

router = APIRouter(prefix="/api/v1/produtor", tags=["Produtor Rural"])

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


@router.get("/{id_produtor}/glebas", response_model=List[RespostaGlebas])
async def consultar_glebas_por_produtor(
        id_produtor: int,
        db_principal: AsyncSession = Depends(get_async_db)
):
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


@router.get("/culturas", status_code=status.HTTP_200_OK)
async def listar_dominio_culturas(
        grupo: Optional[str] = None,
        ativo: Optional[bool] = True,
        db_principal: AsyncSession = Depends(get_async_db)
):
    service = DomínioService(db_principal)
    return await service.obter_dominio_culturas(ativo=ativo, grupo=grupo)
