from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, Row
from typing import List, Optional, Dict, Any

class DomínioRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def calcular_metricas_espaciais(self, wkt: str) -> Optional[Row]:
        query = text("""
            SELECT 
                ROUND((ST_Area(ST_GeomFromText(:wkt, 4326)::geography) / 10000)::numeric, 2) as area_ha,
                ROUND(ST_Perimeter(ST_GeomFromText(:wkt, 4326)::geography)::numeric, 2) as perimetro_m;
        """)
        res = await self.db.execute(query, {"wkt": wkt})
        return res.fetchone()

    async def listar_culturas(self, ativo: Optional[bool], grupo: Optional[str]) -> List[Row]:
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

        res = await self.db.execute(query, parametros)
        return res.fetchall()
