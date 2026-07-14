from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any

from app.repository.dominio_repository import DomínioRepository


class DomínioService:
    def __init__(self, db: AsyncSession):
        self.repo = DomínioRepository(db)
        self.db = db

    async def calcular_area_geometria(self, wkt: str) -> Dict[str, float]:
        try:
            async with self.db.begin():
                resultado = await self.repo.calcular_metricas_espaciais(wkt)

                if not resultado or resultado.area_ha is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Não foi possível processar a geometria fornecida. Verifique se o formato WKT está íntegro."
                    )

                return {
                    "area_hectares": float(resultado.area_ha),
                    "perimetro_metros": float(resultado.perimetro_m)
                }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro interno no PostGIS ao calcular métricas espaciais: {str(e)}"
            )

    async def obter_dominio_culturas(self, ativo: Optional[bool], grupo: Optional[str]) -> List[Dict[str, Any]]:
        try:
            async with self.db.begin():
                culturas = await self.repo.listar_culturas(ativo=ativo, grupo=grupo)

                if not culturas:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Nenhum cultura localizada para os critérios fornecidos."
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
