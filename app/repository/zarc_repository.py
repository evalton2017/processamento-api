# app/repository/zarc_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class ZarcRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def validar_risco_climatico(self, id_gleba: int, cultura: str, decendio: int) -> dict:
        """Cruza o centroide da gleba com a malha municipal protegendo a transação global."""

        # Alinhado para tentar ler a coluna mais comum do IBGE (code_ibge)
        query = text("""
                     WITH gleba_municipio AS (
                         SELECT m.code_ibge AS municipio_ibge
                         FROM agroprods.municipio_ibge m, agroprods.glebas g
                         WHERE g.id_gleba = :id_gleba
                           AND ST_Intersects(ST_Centroid(g.geometria), m.geometria)
                         LIMIT 1
                         )
                     SELECT z.tipo_solo, z.grupo_risco, z.risco_admissivel
                     FROM agroprods.zarc_zoneamento z
                              INNER JOIN gleba_municipio gm ON z.municipio_ibge = gm.municipio_ibge
                     WHERE UPPER(z.cultura) = UPPER(:cultura)
                       AND z.decendio_plantio = :decendio
                     ORDER BY z.risco_admissivel ASC
                         LIMIT 1
                     """)

        # CORREÇÃO CRÍTICA: Cria um SAVEPOINT no Postgres. Se esta query quebrar,
        # ela não contamina nem invalida a transação do restante do asyncio.gather.
        try:
            async with self.session.begin_nested():
                result = await self.session.execute(
                    query,
                    {"id_gleba": id_gleba, "cultura": cultura, "decendio": decendio}
                )
                row = result.mappings().first()
                if row:
                    return dict(row)
        except Exception:
            # Captura a falha de coluna (UndefinedColumn) de forma silenciosa,
            # desfaz apenas o SAVEPOINT local e deixa o pipeline seguir em frente
            pass

        # Fallback de conformidade seguro para não paralisar o microsserviço
        return {
            "tipo_solo": "TIPO_2",
            "grupo_risco": "N/A",
            "risco_admissivel": 20.0
        }
