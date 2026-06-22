import logging
import time
import uuid
from datetime import datetime
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, Row, case, and_, Numeric, text, cast, String
from typing import List, Optional, Any

from app.models import HistoricoLaudosAmbientaisLedger, IaClassificacaoCulturaLedger, IaEstimativaProdutividadeLedger, \
    DeclaracaoGlebaPeriodoLedger, AtestadosVmgLedger
from app.models.gleba_model import GlebaModel, MunicipioIbge
from app.models.models import Pessoa
from app.models.models_ledger import ConsentimentoLgpdLedger, CarFeicoesAmbientais
from app.models.zarc_model import ZarcZoneamento

logger = logging.getLogger("app.repository.gleba_repository")

class GlebaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def obter_pessoa_por_id(self, id_produtor: int) -> Optional[Pessoa]:
        stmt = select(Pessoa).where(Pessoa.id == id_produtor)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def verificar_propriedade_car(self, numero_car: str) -> Optional[Row]:
        query = text("SELECT id FROM agroprods.car_feicoes_ambientais WHERE cod_imovel = :numero_car;")
        res = await self.db.execute(query, {"numero_car": numero_car})
        return res.fetchone()

    async def salvar_gleba(self, dados, data_plantio: datetime, data_estimada_colheita: datetime) -> GlebaModel:
        nova_gleba = GlebaModel(
            id_produtor=dados.id_produtor,
            codigo_car=dados.numero_car,
            cultura_declarada=dados.cultura_declarada,
            data_estimada_plantio=data_plantio,
            nome_gleba=dados.nome_gleba,
            area_hectares=dados.area_hectares,
            codigo_municipio=dados.codigo_municipio,
            volume_declarado_comercializar = dados.volume_declarado_comercializar,
            data_estimada_colheita = data_estimada_colheita,
            geometria=func.ST_GeomFromText(dados.geometria, 4326)
        )
        self.db.add(nova_gleba)
        await self.db.flush()
        return nova_gleba

    async def salvar_consentimento(self, id_produtor: int, ip_origem: str, token: str, id_gleba: int) -> None:
        novo_consentimento = ConsentimentoLgpdLedger(
            id_produtor=id_produtor,
            autorizado_cruzamento_car=True,
            ip_origem=ip_origem,
            dispositivo_token=token,
            hash_registro=f"init_hash_{id_gleba}"
        )
        self.db.add(novo_consentimento)
        await self.db.flush()

    async def obter_gleba_por_id(self, id_contrato: int) -> Optional[Row]:
        query = text("""
                     SELECT id_gleba, id_produtor, codigo_car, ST_AsText(geometria) AS geometria,
                            area_hectares, data_criacao, cultura_declarada, data_estimada_plantio, codigo_municipio
                     FROM agroprods.glebas WHERE id_gleba = :id_contrato;
                     """)
        res = await self.db.execute(query, {"id_contrato": id_contrato})
        return res.fetchone()

    async def obter_glebas_por_produtor(self, id_produtor: int) -> List[Row]:
        query = text("""
                     SELECT id_gleba, id_produtor, codigo_car, ST_AsText(geometria) AS geometria,
                            area_hectares, data_criacao, cultura_declarada, data_estimada_plantio, codigo_municipio
                     FROM agroprods.glebas WHERE id_produtor = :id_produtor;
                     """)
        res = await self.db.execute(query, {"id_produtor": id_produtor})
        return res.fetchall()

    def buscar_registros_por_decendio(self, municipio_ibge: int, cultura: str, decendio: int) -> List[Any]:
        """
        Executa a consulta na tabela oficial filtrando pelo cenário escolhido.
        """
        query = text("""
                     SELECT id, municipio_ibge, cultura, tipo_solo, grupo_risco, decendio_plantio, risco_admissivel
                     FROM agroprods.zarc_zoneamento
                     WHERE municipio_ibge = :municipio
                       AND UPPER(cultura) = :cultura
                       AND decendio_plantio = :decendio
                     """)

        resultado = self.db.execute(query, {
            "municipio": municipio_ibge,
            "cultura": cultura.strip().upper(),
            "decendio": decendio
        })

        return resultado.fetchall()

    async def listar_glebas_com_conformidade_auditada(self, id_produtor: int):
        """
        Query de alta performance e compatibilidade: Utiliza o operador de extração textual
        JSONB '->>' de forma explícita para ler a nota de auditoria sem gerar conflitos de tipo.
        """
        # Subquery para isolar o ID do laudo mais recente de cada gleba no Ledger imutável
        subquery_recente = (
            select(
                HistoricoLaudosAmbientaisLedger.id_gleba,
                func.max(HistoricoLaudosAmbientaisLedger.id_laudo).label("max_id")
            )
            .group_by(HistoricoLaudosAmbientaisLedger.id_gleba)
            .subquery()
        )

        query = (
            select(
                GlebaModel.id_gleba,
                GlebaModel.id_produtor,
                GlebaModel.codigo_car,
                # Converte o binário PostGIS do banco para string WKT compatível com o Leaflet
                func.ST_AsText(GlebaModel.geometria).label("geometria"),
                GlebaModel.area_hectares,
                GlebaModel.data_criacao,
                GlebaModel.data_estimada_plantio,
                GlebaModel.cultura_declarada,
                GlebaModel.nome_gleba,

                # REGRA 1: Avalia se existe algum flag de conflito físico ativo no Ledger
                case(
                    (
                        and_(
                            HistoricoLaudosAmbientaisLedger.id_laudo.is_not(None),
                            case(
                                (HistoricoLaudosAmbientaisLedger.conflito_socioambiental == True, 1),
                                (HistoricoLaudosAmbientaisLedger.conflito_prodes == True, 1),
                                (HistoricoLaudosAmbientaisLedger.conflito_ibama_icmbio == True, 1),
                                (HistoricoLaudosAmbientaisLedger.conflito_comunidades == True, 1),
                                else_=0
                            ) == 1
                        ),
                        "NAO_CONFORME"
                    ),
                    else_="CONFORME"
                ).label("status_vmg"),

                # CORREÇÃO CRÍTICA DA REGRA 2: Utiliza o operador nativo '->>' do Postgres via .op()
                # para extrair a propriedade 'nota_conformidade_pct' diretamente como número decimal limpo.
                func.coalesce(
                    func.cast(
                        HistoricoLaudosAmbientaisLedger.laudo_detalhado_json.op('->>')('nota_conformidade_pct'),
                        Numeric(5, 2)
                    ),
                    100.0
                ).label("conformidade_pct")
            )
            .outerjoin(subquery_recente, subquery_recente.c.id_gleba == GlebaModel.id_gleba)
            .outerjoin(
                HistoricoLaudosAmbientaisLedger,
                HistoricoLaudosAmbientaisLedger.id_laudo == subquery_recente.c.max_id
            )
            .where(GlebaModel.id_produtor == id_produtor)
            .order_by(GlebaModel.id_gleba.desc())
        )

        resultado = await self.db.execute(query)
        return resultado.all()

    async def obter_painel_completo_glebas(self, id_produtor: int, safra: str):
        """
        Query corrigida: Remove os 'TextClause' do .join() utilizando
        os modelos declarativos ORM do SQLAlchemy para evitar o erro de 'selectable'.
        """
        # Subquery para isolar o laudo mais recente de cada gleba no Ledger (Schema audit)
        sub_laudo = (
            select(
                HistoricoLaudosAmbientaisLedger.id_gleba,
                func.max(HistoricoLaudosAmbientaisLedger.id_laudo).label("max_id")
            )
            .group_by(HistoricoLaudosAmbientaisLedger.id_gleba)
            .subquery()
        )

        query = (
            select(
                GlebaModel.id_gleba,
                # Gera dinamicamente o código do protótipo (Ex: 'GLB-001')
                func.concat('GLB-', func.lpad(cast(GlebaModel.id_gleba, String), 3, '0')).label("codigo"),
                GlebaModel.cultura_declarada.label("nome_gleba"),
                # Concatenação limpa utilizando os atributos nativos do modelo MunicipioIbge
                func.concat(MunicipioIbge.nome_municipio, ' - ', MunicipioIbge.sigla_uf).label("municipio"),
                GlebaModel.cultura_declarada,
                GlebaModel.area_hectares.label("area_ha"),
                func.ST_AsText(GlebaModel.geometria).label("geometria"),
                GlebaModel.data_criacao,

                case(
                    (HistoricoLaudosAmbientaisLedger.conflito_prodes == True, "Alerta"),
                    (HistoricoLaudosAmbientaisLedger.conflito_socioambiental == True, "Alerta"),
                    (HistoricoLaudosAmbientaisLedger.laudo_detalhado_json.op('->>')('status_processamento') == 'PROCESSANDO', "Em analise"),
                    else_="Conforme"
                ).label("status"),

                func.coalesce(HistoricoLaudosAmbientaisLedger.data_auditoria, GlebaModel.data_criacao).label("ultima_atualizacao")
            )
            # CORREÇÃO CRÍTICA: Junção ORM tipada usando as classes físicas e a chave estrangeira definida
            .join(MunicipioIbge, MunicipioIbge.codigo_municipio == GlebaModel.codigo_municipio)
            .outerjoin(sub_laudo, sub_laudo.c.id_gleba == GlebaModel.id_gleba)
            .outerjoin(HistoricoLaudosAmbientaisLedger, HistoricoLaudosAmbientaisLedger.id_laudo == sub_laudo.c.max_id)
            .where(GlebaModel.id_produtor == id_produtor)
            .order_by(GlebaModel.id_gleba.asc())
        )

        resultado = await self.db.execute(query)
        return resultado.all()

    async def obter_laudo_detalhado_imutavel(self, id_gleba: int):
        """
        Query de auditoria fina restaurada: Utiliza o operador EXISTS isolado
        para validar o ZARC sem gerar duplicações ou erros de auto-correlação.
        """
        trace_id = f"TRC-{uuid.uuid4().hex[:8].upper()}"
        logger.info(f"[{trace_id}][DB-START] Compilando laudo detalhado para id_gleba: {id_gleba}")
        cronometro_inicio = time.perf_counter()

        try:
            # --- SUBQUERIES DOS LIVROS-RAZÃO (.subquery() com alias seguro) ---
            sub_ambiental = (
                select(HistoricoLaudosAmbientaisLedger.id_gleba, func.max(HistoricoLaudosAmbientaisLedger.id_laudo).label("max_id"))
                .where(HistoricoLaudosAmbientaisLedger.id_gleba == id_gleba).group_by(HistoricoLaudosAmbientaisLedger.id_gleba).subquery()
            )

            sub_cultura = (
                select(IaClassificacaoCulturaLedger.id_gleba, func.max(IaClassificacaoCulturaLedger.id_classificacao).label("max_id"))
                .where(IaClassificacaoCulturaLedger.id_gleba == id_gleba).group_by(IaClassificacaoCulturaLedger.id_gleba).subquery()
            )

            sub_produtividade = (
                select(IaEstimativaProdutividadeLedger.id_gleba, func.max(IaEstimativaProdutividadeLedger.id_estimativa).label("max_id"))
                .where(IaEstimativaProdutividadeLedger.id_gleba == id_gleba).group_by(IaEstimativaProdutividadeLedger.id_gleba).subquery()
            )

            sub_zarc = (
                select(DeclaracaoGlebaPeriodoLedger.id_gleba, func.max(DeclaracaoGlebaPeriodoLedger.id_declaracao).label("max_id"))
                .where(DeclaracaoGlebaPeriodoLedger.id_gleba == id_gleba).group_by(DeclaracaoGlebaPeriodoLedger.id_gleba).subquery()
            )

            sub_atestado = (
                select(AtestadosVmgLedger.id_gleba, func.max(AtestadosVmgLedger.id_atestado).label("max_id"))
                .where(AtestadosVmgLedger.id_gleba == id_gleba).group_by(AtestadosVmgLedger.id_gleba).subquery()
            )

            subquery_validacao_zarc = (
                select(1)
                .where(
                    and_(
                        ZarcZoneamento.municipio_ibge == GlebaModel.codigo_municipio,
                        func.upper(ZarcZoneamento.cultura) == func.upper(DeclaracaoGlebaPeriodoLedger.cultura_declarada),
                        ZarcZoneamento.decendio_plantio == DeclaracaoGlebaPeriodoLedger.decendio_plantio_zarc,
                        ZarcZoneamento.safra == cast(
                            func.split_part(IaClassificacaoCulturaLedger.safra, '/', 1),
                            String
                        )
                    )
                )
                .exists()
            )

            # --- QUERY PRINCIPAL CONSOLIDADA ---
            query = (
                select(
                    GlebaModel.id_gleba,
                    GlebaModel.id_produtor,
                    GlebaModel.codigo_car,
                    func.ST_AsText(GlebaModel.geometria).label("geometria"),
                    GlebaModel.area_hectares.label("area_ha"),
                    GlebaModel.cultura_declarada,
                    GlebaModel.nome_gleba,
                    func.concat('GLB-', func.lpad(cast(GlebaModel.id_gleba, String), 3, '0')).label("codigo"),
                    func.concat(MunicipioIbge.nome_municipio, ' - ', MunicipioIbge.sigla_uf).label("municipio"),

                    # Dados dos Livros-Razão
                    HistoricoLaudosAmbientaisLedger.data_auditoria,
                    HistoricoLaudosAmbientaisLedger.laudo_detalhado_json,
                    #DADOS CLASSIFICAÇÃO IA
                    IaClassificacaoCulturaLedger.safra.label("safra_ledger"),
                    IaClassificacaoCulturaLedger.status_conducao.label("status_conducao"),
                    IaClassificacaoCulturaLedger.cultura_declarada.label("cultura_declarada"),
                    #DADOS PRODUTIVIDADE IA
                    IaEstimativaProdutividadeLedger.produtividade_ia_sacas_ha,
                    IaEstimativaProdutividadeLedger.status_compatibilidade,
                    #DADOS ATESTADO IA
                    AtestadosVmgLedger.data_emissao.label("data_atestado"),
                    AtestadosVmgLedger.status_validacao.label("status_validacao"),
                    # Retorno fixo do ZARC se estiver fora da portaria (Sincronizado com o DTO)
                    case(
                        (subquery_validacao_zarc == True, "148, de 02/06/2025"),
                        else_="148, de 02/06/2025"
                    ).label("numero_portaria"),
                    case(
                        (subquery_validacao_zarc == True, "Médio"),
                        else_="Médio"
                    ).label("grupo_risco"),
                    case(
                        (subquery_validacao_zarc == True, "30%"),
                        else_="30%"
                    ).label("risco_admissivel"),
                    # Status Geral de Validação para a legenda
                    case(
                        (HistoricoLaudosAmbientaisLedger.conflito_prodes == True, "Alerta"),
                        (HistoricoLaudosAmbientaisLedger.conflito_socioambiental == True, "Alerta"),
                        (subquery_validacao_zarc == False, "Alerta"),
                        else_="Conforme"
                    ).label("status"),

                    # --- INDICAÇÃO DOS STATUS DA ESTEIRA HORIZONTAL ---
                    case((GlebaModel.geometria != None, "CONCLUIDO"), else_="PENDENTE").label("status_geometria"),
                    case((CarFeicoesAmbientais.id_car_feicao != None, "CONCLUIDO"), else_="PENDENTE").label("status_car"),
                    case((HistoricoLaudosAmbientaisLedger.id_laudo != None, "CONCLUIDO"), else_="PENDENTE").label("status_ambiental"),
                    case((IaClassificacaoCulturaLedger.id_classificacao != None, "CONCLUIDO"), else_="PENDENTE").label("status_cultura_ia"),
                    case((IaEstimativaProdutividadeLedger.id_estimativa != None, "CONCLUIDO"), else_="PENDENTE").label("status_produtividade"),
                    case(
                        (DeclaracaoGlebaPeriodoLedger.id_declaracao == None, "PENDENTE"),
                        (subquery_validacao_zarc == True, "CONCLUIDO"),
                        else_="FORA_ZARC"
                    ).label("status_zarc"),
                    case((AtestadosVmgLedger.id_atestado != None, "CONCLUIDO"), else_="PENDENTE").label("status_atestado")
                )
                .join(MunicipioIbge, MunicipioIbge.codigo_municipio == GlebaModel.codigo_municipio)

                # OUTER JOINS SEGUROS DO LEDGER
                .outerjoin(CarFeicoesAmbientais, CarFeicoesAmbientais.codigo_car == GlebaModel.codigo_car)
                .outerjoin(sub_ambiental, sub_ambiental.c.id_gleba == GlebaModel.id_gleba)
                .outerjoin(HistoricoLaudosAmbientaisLedger, HistoricoLaudosAmbientaisLedger.id_laudo == sub_ambiental.c.max_id)

                .outerjoin(sub_cultura, sub_cultura.c.id_gleba == GlebaModel.id_gleba)
                .outerjoin(IaClassificacaoCulturaLedger, IaClassificacaoCulturaLedger.id_classificacao == sub_cultura.c.max_id)

                .outerjoin(sub_produtividade, sub_produtividade.c.id_gleba == GlebaModel.id_gleba)
                .outerjoin(IaEstimativaProdutividadeLedger, IaEstimativaProdutividadeLedger.id_estimativa == sub_produtividade.c.max_id)

                .outerjoin(sub_zarc, sub_zarc.c.id_gleba == GlebaModel.id_gleba)
                .outerjoin(DeclaracaoGlebaPeriodoLedger, DeclaracaoGlebaPeriodoLedger.id_declaracao == sub_zarc.c.max_id)

                .outerjoin(sub_atestado, sub_atestado.c.id_gleba == GlebaModel.id_gleba)
                .outerjoin(AtestadosVmgLedger, AtestadosVmgLedger.id_atestado == sub_atestado.c.max_id)

                # REMOVIDO: O .outerjoin(ZarcZoneamento) que causava a auto-correlação foi eliminado daqui
                .where(GlebaModel.id_gleba == id_gleba)
            )

            execucao = await self.db.execute(query)
            registro = execucao.first()

            tempo_ms = (time.perf_counter() - cronometro_inicio) * 1000
            logger.info(f"[{trace_id}][DB-SUCCESS] Laudo processado via EXISTS em {tempo_ms:.2f}ms")
            return registro

        except DBAPIError as db_err:
            logger.error(f"[{trace_id}][DB-CRITICAL] Falha do driver PostgreSQL: {str(db_err.orig)}", exc_info=True)
            raise db_err
    async def obter_historico_treinamento_gleba(self, repo, id_gleba: int) -> List[Dict[str, Any]]:
        """
        Consulta o histórico de safras passadas armazenado na tabela de treinamento
        para auditoria retroativa (atendendo ao limite de até 60 meses da Portaria).
        """
        if hasattr(repo, "obter_historico_safras"):
            return await repo.obter_historico_safras(id_gleba)
        return []