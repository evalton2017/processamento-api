from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, Row, case, and_, Numeric
from typing import List, Optional, Any, cast

from app.models import HistoricoLaudosAmbientaisLedger
from app.models.gleba_model import GlebaModel
from app.models.models import Pessoa
from app.models.models_ledger import ConsentimentoLgpdLedger


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