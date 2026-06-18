import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.repository.dashboard_produtor_repository import DashboardProdutorRepository

logger = logging.getLogger(__name__)

class DashboardProdutorService:
    def __init__(self, db_session: AsyncSession):
        self.repository = DashboardProdutorRepository(db_session)

    async def obter_dados_dashboard_produtor(self, id_produtor: int, safra: str) -> Dict[str, Any]:
        logger.info(f"Gerando consolidação de KPIs do painel do produtor {id_produtor} para safra {safra}.")

        nome_produtor = await self.repository.obter_nome_produtor(id_produtor)
        metricas = await self.repository.consultar_metricas_consolidadas(id_produtor, safra)

        total_glebas = int(metricas["total_glebas"])
        area_total = float(metricas["area_total"])
        area_conforme = float(metricas["area_conforme"])

        pct_monitoramento = 100.0 if total_glebas > 0 else 0.0
        pct_conformidade = (area_conforme / area_total * 100) if area_total > 0 else 100.0

        # Simulação do agendamento contínuo guiado pela portaria VMG
        data_agendada = datetime.now() + timedelta(days=15)
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
