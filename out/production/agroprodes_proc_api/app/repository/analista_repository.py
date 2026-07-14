from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from typing import Dict, Any, List

class AnalistaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _aplicar_filtros_modelo_ledger(self, query, filtros: Dict[str, Any]):
        if filtros.get("municipio") and filtros["municipio"] != "Todos":
            query = query.where(text("m.nome_municipio = :municipio")).params(municipio=filtros["municipio"])

        if filtros.get("cultura") and filtros["cultura"] != "Todos":
            query = query.where(text("cl.cultura_identificada = :cultura")).params(cultura=filtros["cultura"])

        if filtros.get("conformidade_ambiental") and filtros["conformidade_ambiental"] != "Todos":
            if filtros["conformidade_ambiental"] == "Conforme":
                query = query.where(text("hl.conflito_socioambiental = FALSE"))
            elif filtros["conformidade_ambiental"] == "Não Conforme":
                query = query.where(text("hl.conflito_socioambiental = TRUE"))

        if filtros.get("car"):
            query = query.where(text("g.codigo_car ILIKE :car")).params(car=f"%{filtros['car']}%")
        if filtros.get("cpf_cnpj"):
            query = query.where(text("p.cpf_cnpj = :cpf_cnpj")).params(cpf_cnpj=filtros["cpf_cnpj"])

        return query

    def _aplicar_ordenacao_modelo_ledger(self, query, ordenar_por: str):
        if ordenar_por == "Mais recentes":
            return query.order_by(text("cl.data_analise DESC NULLS LAST"))
        return query.order_by(text("g.id_gleba DESC"))

    async def contar_total_glebas(self, filtros: Dict[str, Any]) -> int:
        # CORREÇÃO CRÍTICA: Vinculação por id_gleba E hash_bloco para evitar cartesiano
        sql_base = (
            "agroprods.glebas g "
            "JOIN agroprods.pessoa p ON g.id_produtor = p.id "
            "JOIN audit.atestados_vmg_ledger am ON g.id_gleba = am.id_gleba "
            "JOIN audit.ia_classificacao_cultura_ledger cl ON g.id_gleba = cl.id_gleba AND am.hash_relatorio = cl.hash_bloco "
            "JOIN audit.historico_laudos_ambientais_ledger hl ON g.id_gleba = hl.id_gleba AND am.hash_relatorio = hl.hash_bloco "
            "LEFT JOIN agroprods.municipio_ibge m ON g.codigo_municipio = m.codigo_municipio "
            "WHERE cl.safra = :safra "
        )
        query = select(func.count()).select_from(text(sql_base)).params(safra=filtros["safra"])
        query = self._aplicar_filtros_modelo_ledger(query, filtros)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def listar_glebas_modelo_ledger(self, filtros: Dict[str, Any], page: int, limit: int) -> List[Dict[str, Any]]:
        offset = (page - 1) * limit

        # CORREÇÃO CRÍTICA: Vinculação por id_gleba E hash_bloco para evitar cartesiano
        sql_base = (
            "agroprods.glebas g "
            "JOIN agroprods.pessoa p ON g.id_produtor = p.id "
            "JOIN audit.atestados_vmg_ledger am ON g.id_gleba = am.id_gleba "
            "JOIN audit.ia_classificacao_cultura_ledger cl ON g.id_gleba = cl.id_gleba AND am.hash_relatorio = cl.hash_bloco "
            "JOIN audit.historico_laudos_ambientais_ledger hl ON g.id_gleba = hl.id_gleba AND am.hash_relatorio = hl.hash_bloco "
            "LEFT JOIN agroprods.municipio_ibge m ON g.codigo_municipio = m.codigo_municipio "
            "WHERE cl.safra = :safra "
        )

        query = select(
            text("g.codigo_car as car"),
            text("p.nome as produtor"),
            text("m.nome_municipio || ' - ' || m.codigo_uf as municipio"),
            text("cl.cultura_identificada as cultura"),
            text("g.area_hectares as area_ha"),
            text("cl.safra as safra"),
            text("CASE WHEN hl.conflito_socioambiental = TRUE THEN 'Não Conforme' ELSE 'Conforme' END as conformidade_ambiental"),
            text("CASE WHEN am.status_validacao = 'REPROVADO' THEN 'Bloqueada' ELSE 'Monitorada' END as status_gleba"),
            text("TO_CHAR(cl.data_analise, 'DD/MM/YYYY') as atualizacao")
        ).select_from(text(sql_base)).params(safra=filtros["safra"]).offset(offset).limit(limit)

        query = self._aplicar_filtros_modelo_ledger(query, filtros)
        query = self._aplicar_ordenacao_modelo_ledger(query, filtros.get("ordenar_por", "Mais recentes"))

        result = await self.session.execute(query)
        return result.mappings().all()
