from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.gleba_model import GlebaModel
from app.models.gleba_model import MunicipioIbge
from app.models.classificacao_model import CertificadosBpa
from app.models.classificacao_model import  ClassificacoesCulturas
from app.models.embargos_model import EmbargosOrgaos
from app.models.notificacao_model import NotificacaoUsuarioModel

class DashboardRepository:
    def __init__(self, db: AsyncSession):
        self.db = db


    async def cadastrar_gleba_prototipo(self, dados: dict) -> GlebaModel:
        """Insere a gleba mapeando todos os campos do fluxo de 5 etapas do protótipo."""

        sql_query = """
                    INSERT INTO agroprods.glebas
                    (id_produtor, codigo_car, cultura_declarada, geometria, area_hectares,
                     codigo_municipio, data_estimada_plantio, data_criacao)
                    VALUES
                        (:id_produtor, :id_car_vinculado, :cultura_declarada, ST_GeomFromText(:geometria, 4326),
                         :area_hectares, :codigo_municipio, :data_estimada_plantio, NOW())
                        RETURNING id_gleba, id_produtor, codigo_car, cultura_declarada, area_hectares, codigo_municipio, data_estimada_plantio, data_criacao; \
                    """

        result = await self.db.execute(text(sql_query), {
            "id_produtor": dados["id_produtor"],
            "id_car_vinculado": dados["id_car_vinculado"],
            "cultura_declarada": dados["cultura_declarada"],
            "geometria": dados["geometria"],
            "area_hectares": dados["area_hectares"],
            "codigo_municipio": dados["codigo_municipio"],
            "data_estimada_plantio": dados["data_estimada_plantio"]
        })

        row = result.first()
        await self.db.commit()

        # Cria a instância mockando dados extras exigidos pelo DTO de resposta da tela final
        return GlebaModel(
            id_gleba=row.id_gleba,
            id_produtor=row.id_produtor,
            codigo_car=row.codigo_car,
            area_hectares=row.area_hectares,
            cultura_declarada=row.cultura_declarada,
            data_criacao=row.data_criacao
        )

    async def get_kpis(self, safra: str, estado: str = "Todos") -> dict:
        """Calcula os agregados numéricos usando a sintaxe select do SQLAlchemy Async."""
        # 1. Query de Glebas
        stmt_glebas = select(
            func.count(func.distinct(GlebaModel.id_produtor)).label("total_contratos"),
            func.count(GlebaModel.id_gleba).label("total_glebas"),
            func.sum(GlebaModel.area_hectares).label("area_total")
        )

        if estado != "Todos":
            stmt_glebas = stmt_glebas.join(
                MunicipioIbge, MunicipioIbge.codigo_municipio == GlebaModel.codigo_municipio
            ).filter(MunicipioIbge.sigla_uf == estado)

        exec_glebas = await self.db.execute(stmt_glebas)
        glebas_data = exec_glebas.first()

        # 2. Alertas Ativos
        stmt_alertas = select(func.count(EmbargosOrgaos.id)).filter(EmbargosOrgaos.situacao == "Ativo")
        exec_alertas = await self.db.execute(stmt_alertas)
        total_alertas = exec_alertas.scalar() or 0

        # 3. Atestados Emitidos
        stmt_atestados = select(func.count(CertificadosBpa.id))
        exec_atestados = await self.db.execute(stmt_atestados)
        total_atestados = exec_atestados.scalar() or 0

        return {
            "contratos": {"valor_atual": glebas_data.total_contratos or 0, "variacao_percentual": 8.2, "sufixo": ""},
            "glebas_monitoradas": {"valor_atual": glebas_data.total_glebas or 0, "variacao_percentual": 5.7, "sufixo": ""},
            "area_total": {"valor_atual": float(glebas_data.area_total or 0), "variacao_percentual": 7.1, "sufixo": "ha"},
            "alertas_ativos": {"valor_atual": total_alertas, "variacao_percentual": -12.4, "sufixo": ""},
            "atestados_emitidos": {"valor_atual": total_atestados, "variacao_percentual": 9.2, "sufixo": ""}
        }

    async def get_contratos_por_cultura(self, safra: str) -> list:
        """Alimenta o gráfico de rosca de forma assíncrona."""
        stmt = (
            select(
                ClassificacoesCulturas.cultura_predita.label("cultura"),
                func.count(ClassificacoesCulturas.id).label("quantidade")
            )
            .filter(ClassificacoesCulturas.safra == safra)
            .group_by(ClassificacoesCulturas.cultura_predita)
        )

        exec_res = await self.db.execute(stmt)
        resultados = exec_res.all()

        total_geral = sum(r.quantidade for r in resultados) or 1

        return [
            {
                "cultura": r.cultura or "Outros",
                "quantidade": r.quantidade,
                "percentual": round((r.quantidade / total_geral) * 100, 1)
            }
            for r in resultados
        ]

    async def get_contratos_por_estado(self, safra: str) -> list:
        """Alimenta o gráfico de barras de forma assíncrona."""
        stmt = (
            select(
                MunicipioIbge.sigla_uf.label("estado"),
                func.count(func.distinct(GlebaModel.id_produtor)).label("quantidade")
            )
            .join(MunicipioIbge, MunicipioIbge.codigo_municipio == GlebaModel.codigo_municipio)
            .group_by(MunicipioIbge.sigla_uf)
            .order_by(func.count(func.distinct(GlebaModel.id_produtor)).desc())
        )

        exec_res = await self.db.execute(stmt)
        resultados = exec_res.all()
        return [{"estado": r.estado, "quantidade": r.quantidade} for r in resultados if r.estado]

    async def get_mapa_status_estados(self) -> list:
        """Classificação de risco do mapa de forma assíncrona."""
        stmt = (
            select(
                MunicipioIbge.sigla_uf.label("estado"),
                func.count(NotificacaoUsuarioModel.id).label("total_alertas") # 🟢 Alterado aqui
            )
            .join(GlebaModel, GlebaModel.id_gleba == NotificacaoUsuarioModel.id_gleba) # 🟢 Alterado aqui
            .join(MunicipioIbge, MunicipioIbge.codigo_municipio == GlebaModel.codigo_municipio)
            .group_by(MunicipioIbge.sigla_uf)
        )

        exec_res = await self.db.execute(stmt)
        resultados = exec_res.all()

        status_mapa = []
        for r in resultados:
            status = "Alerta" if r.total_alertas > 50 else ("Atenção" if r.total_alertas > 15 else "Normal")
            status_mapa.append({"estado": r.estado, "status": status})
        return status_mapa

    async def get_eventos_recentes(self, limit: int = 5) -> list:
        """Retorna o feed de últimas ocorrências de forma assíncrona."""
        stmt = (
            select(NotificacaoUsuarioModel)
            .order_by(NotificacaoUsuarioModel.data_criacao.desc())
            .limit(limit)
        )

        exec_res = await self.db.execute(stmt)
        eventos = exec_res.scalars().all()

        return [
            {
                "id": e.id,
                "descricao": e.tipo or "Evento registrado",
                "data_hora": e.data_criacao.strftime("%d/%m/%Y %H:%M") if e.data_criacao else "",
                "status": e.status or "Atenção"
            }
            for e in eventos
        ]
