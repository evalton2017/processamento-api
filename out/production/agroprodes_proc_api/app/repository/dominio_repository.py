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
                     SELECT DISTINCT ON (LOWER(z.cultura))
                         z.id AS id,
                         UPPER(SUBSTRING(z.cultura FROM 1 FOR 3)) AS codigo, -- Gera um código de 3 letras (Ex: SOJ, ARR)
                         INITCAP(z.cultura) AS nome,                         -- Capitaliza o nome (Ex: Soja, Arroz, Feijão)
                         'GRÃOS' AS grupo,                                   -- Classificação padrão de grupo regulatório
                         TRUE AS ativo,                                      -- Compatibilidade de flag com o DTO anterior
                         TRUE AS permite_zarc,                               -- Garante conformidade com o ecossistema VMG
                         z.data_atualizacao AS data_cadastro
                     FROM agroprods.zarc_zoneamento z
                     ORDER BY LOWER(z.cultura) ASC, z.id ASC;
                     """)


        res = await self.db.execute(query, parametros)
        return res.fetchall()
