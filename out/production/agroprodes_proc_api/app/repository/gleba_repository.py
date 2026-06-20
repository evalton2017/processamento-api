from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, Row
from typing import List, Optional

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
