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

        query = text("""
                     WITH culturas_agrupadas AS (
                         SELECT
                             MIN(z.id) AS id, -- Pega o menor ID para cada cultura (simula o z.id ASC)
                             LOWER(z.cultura) AS cultura_lower,
                             MAX(z.data_atualizacao) AS data_atualizacao -- Ajuste para MIN ou MAX conforme sua regra
                         FROM agroprods.zarc_zoneamento z
                         GROUP BY LOWER(z.cultura)
                     )
                     SELECT
                         id,
                         UPPER(SUBSTRING(cultura_lower FROM 1 FOR 3)) AS codigo,
                         INITCAP(cultura_lower) AS nome,
                         'GRÃOS' AS grupo,
                         TRUE AS ativo,
                         TRUE AS permite_zarc,
                         data_atualizacao AS data_cadastro
                     FROM culturas_agrupadas
                     ORDER BY cultura_lower ASC;
                     """)


        res = await self.db.execute(query, parametros)
        return res.fetchall()
