import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.dto.gleba_dto import GlebaCreateInput, GlebaResponse
from app.repository.dashboard_repository import DashboardRepository

logger = logging.getLogger(__name__)

class DashboardService:
    def __init__(self, db: AsyncSession):
        """
        Inicializa o serviço recebendo a sessão assíncrona de banco de dados
        e instanciando seu respectivo repositório.
        """
        self.db = db
        self.repository = DashboardRepository(db)

    async def criar_nova_gleba(self, input_data: GlebaCreateInput) -> GlebaResponse:
        """Processa o payload unificado gerado pelas 5 etapas do formulário."""
        payload = input_data.model_dump()

        # Grava os dados essenciais no banco de dados
        nova_gleba = await self.repository.cadastrar_gleba_prototipo(payload)

        # Formata a resposta com as informações que o protótipo exige na tela final
        return GlebaResponse(
            id_gleba=nova_gleba.id_gleba,
            nome_gleba=input_data.nome_gleba,
            id_produtor=nova_gleba.id_produtor,
            codigo_car=nova_gleba.codigo_car,
            area_hectares=nova_gleba.area_hectares,
            cultura_declarada=nova_gleba.cultura_declarada,
            safra=input_data.safra,
            status="Em Validação", # Texto exato exibido no card de sucesso do protótipo
            data_criacao=nova_gleba.data_criacao
        )

    async def obter_dados_dashboard(self, safra: str, estado: str = "Todos") -> dict:
        """
        Orquestra e consolida todas as informações necessárias para renderizar
        a tela inicial do Dashboard em uma única chamada assíncrona.
        """
        try:
            if not estado:
                estado = "Todos"

            logger.info(f"📊 Compilando dados do dashboard para a Safra: {safra} | Estado: {estado}")

            # Executa e aguarda as consultas assíncronas do repositório
            kpis = await self.repository.get_kpis(safra=safra, estado=estado)
            por_cultura = await self.repository.get_contratos_por_cultura(safra=safra)
            por_estado = await self.repository.get_contratos_por_estado(safra=safra)
            status_mapa = await self.repository.get_mapa_status_estados()
            eventos = await self.repository.get_eventos_recentes(limit=5)

            return {
                "sucesso": True,
                "safra_consultada": safra,
                "estado_filtrado": estado,
                "dados": {
                    "kpis": kpis,
                    "grafico_culturas": por_cultura,
                    "grafico_estados": por_estado,
                    "mapa_risco": status_mapa,
                    "feed_eventos": eventos
                }
            }

        except Exception as e:
            logger.error(f"❌ Erro ao compilar dados consolidados do dashboard: {str(e)}", exc_info=True)
            return {
                "sucesso": False,
                "mensagem": "Não foi possível carregar os dados consolidados do dashboard.",
                "erro": str(e)
            }

    async def obter_kpis_topo(self, safra: str, estado: str = "Todos") -> dict:
        """Busca isolada apenas para os cards numéricos superiores."""
        try:
            dados = await self.repository.get_kpis(safra, estado)
            return {"sucesso": True, "data": dados}
        except Exception as e:
            logger.error(f"❌ Erro ao buscar KPIs: {str(e)}")
            return {"sucesso": False, "mensagem": "Erro ao carregar blocos de indicadores."}

    async def obter_distribuicao_culturas(self, safra: str) -> dict:
        """Busca isolada para atualizar apenas o gráfico de rosca (Culturas)."""
        try:
            dados = await self.repository.get_contratos_por_cultura(safra)
            return {"sucesso": True, "data": dados}
        except Exception as e:
            logger.error(f"❌ Erro ao buscar distribuição por cultura: {str(e)}")
            return {"sucesso": False, "mensagem": "Erro ao carregar gráfico de culturas."}

    async def obter_distribuicao_estados(self, safra: str) -> dict:
        """Busca isolada para atualizar apenas o gráfico de barras (Estados)."""
        try:
            dados = await self.repository.get_contratos_por_estado(safra)
            return {"sucesso": True, "data": dados}
        except Exception as e:
            logger.error(f"❌ Erro ao buscar contratos por estado: {str(e)}")
            return {"sucesso": False, "mensagem": "Erro ao carregar gráfico regional."}

    async def obter_alertas_mapa(self) -> dict:
        """Busca isolada para renderizar as camadas de calor ou status do mapa geográfico."""
        try:
            dados = await self.repository.get_mapa_status_estados()
            return {"sucesso": True, "data": dados}
        except Exception as e:
            logger.error(f"❌ Erro ao buscar status do mapa: {str(e)}")
            return {"sucesso": False, "mensagem": "Erro ao carregar criticidade do mapa."}

    async def obter_ultimos_eventos(self, limite: int = 5) -> dict:
        """Busca isolada para atualizar o feed de logs de notificações em tempo real."""
        try:
            dados = await self.repository.get_eventos_recentes(limit=limite)
            return {"sucesso": True, "data": dados}
        except Exception as e:
            logger.error(f"❌ Erro ao buscar feed de eventos: {str(e)}")
            return {"sucesso": False, "mensagem": "Erro ao processar notificações recentes."}
