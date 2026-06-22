import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.repository.produtor_repository import ProdutorRepository
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ProdutorService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.repository = ProdutorRepository(db_session)
        self.repo = self.repository

    async def obter_dados_dashboard_produtor(self, id_produtor: int, safra: str) -> Dict[str, Any]:
        logger.info(f"Consolidando dados da tela do produtor ID {id_produtor} para a safra {safra}.")

        # 1. Recupera o nome da pessoa de forma isolada
        nome_produtor = await self.repository.obter_nome_produtor(id_produtor)

        # 2. Executa a query de KPIs agregados do banco de dados
        metricas = await self.repository.consultar_metricas_consolidadas(id_produtor, safra)

        # 3. Processamento e cálculo de percentuais com blindagem contra divisão por zero
        total_glebas = int(metricas["total_glebas"])
        area_total = float(metricas["area_total"])
        area_conforme = float(metricas["area_conforme"])

        pct_monitoramento = 100.0 if total_glebas > 0 else 0.0
        pct_conformidade = (area_conforme / area_total * 100) if area_total > 0 else 100.0

        # 4. Regra de negócio para a próxima validação automática agendada (Portaria)
        data_agendada = datetime.now() + timedelta(days=27)
        proxima_validacao_str = data_agendada.strftime("%d/%m/%Y")

        return {
            "produtor_nome": nome_produtor,
            "safra_selecionada": safra,
            "glebas_ativas_total": total_glebas,
            "glebas_monitoradas_pct": round(pct_monitoramento, 1),
            "conformidade_ambiental_pct": round(pct_conformidade, 1),
            "area_conforme_ha": round(area_conforme, 2),
            "area_total_ha": round(area_total, 2),
            "total_municipios": int(metricas["total_municipios"]),
            "atestados_emitidos_total": int(metricas["total_atestados"]),
            "alertas_total": int(metricas["total_alertas"]),
            "proxima_validacao_data": proxima_validacao_str
        }

    async def buscar_detalhes_car(self, numero_car: str) -> Dict[str, Any]:
        try:
            async with self.db.begin():
                feicoes = await self.repository.obter_feicoes_ambientais_car(numero_car)

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

    async def listar_municipios(self) -> List[Dict[str, Any]]:
        try:
            async with self.db.begin():
                linhas = await self.repository.obter_todos_municipios()

                return [
                    {
                        "codigo_municipio": m.codigo_municipio,
                        "nome_municipio": m.nome_municipio,
                        "sigla_uf": m.sigla_uf,
                        "estado": m.estado
                    }
                    for m in linhas
                ]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao recuperar a lista de municípios: {str(e)}",
            )

    async def identificar_municipio_por_coordenadas(self, lat: float, lon: float) -> Dict[str, Any]:
        try:
            async with self.db.begin():
                municipio = await self.repository.buscar_municipio_por_coordenadas(lat, lon)

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


