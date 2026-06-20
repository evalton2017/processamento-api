# app/services/produtor/validacao_zarc_service.py
from datetime import date, datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status
from pydantic import BaseModel

from app.models.zarc_model import ZarcZoneamento


class PlanejamentoAgronomicoDTO(BaseModel):
    id_gleba: int
    municipio_ibge: int
    cultura: str
    safra: str
    volume_declarado: float
    data_plantio: date
    data_colheita: date

class ValidacaoZarcService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _calcular_decendio(self, data: date) -> int:
        dia = data.day
        mes = data.month
        decendio_mes = 1 if dia <= 10 else (2 if dia <= 20 else 3)
        return ((mes - 1) * 3) + decendio_mes

    def _converter_decendio_para_texto(self, decendio: int) -> str:
        meses = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ]
        mes_idx = (decendio - 1) // 3
        posicao_mes = (decendio - 1) % 3
        nome_mes = meses[mes_idx]
        if posicao_mes == 0:
            return f"01 a 10 de {nome_mes}"
        elif posicao_mes == 1:
            return f"11 a 20 de {nome_mes}"
        else:
            return f"21 a no máximo 31 de {nome_mes}"

    async def _buscar_janelas_permitidas(self, municipio_ibge: int, cultura: str) -> list:
        query = (
            select(ZarcZoneamento.decendio_plantio, ZarcZoneamento.risco_admissivel)
            .where(
                and_(
                    ZarcZoneamento.municipio_ibge == municipio_ibge,
                    ZarcZoneamento.cultura.ilike(cultura),
                    ZarcZoneamento.risco_admissivel <= 20.00
                )
            )
            .order_by(ZarcZoneamento.decendio_plantio.asc())
        )
        execucao = await self.db.execute(query)
        registros = execucao.all()
        return [
            {
                "decendio": r.decendio_plantio,
                "periodo_sugerido": self._converter_decendio_para_texto(r.decendio_plantio),
                "risco_pct": float(r.risco_admissivel)
            }
            for r in registros
        ]

    async def validar_planejamento_zarc(self, dados) -> dict:
        # CORREÇÃO CRÍTICA 1: Sincronização dos nomes dos atributos com o DTO Pydantic
        if dados.data_estimada_colheita <= dados.data_estimada_plantio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A data estimada da colheita deve ser posterior à data de plantio."
            )

        # CORREÇÃO CRÍTICA 2: Acessando a propriedade correta do DTO para o cálculo do decêndio
        decendio_proposto = self._calcular_decendio(dados.data_estimada_plantio)

        query_zarc = (
            select(ZarcZoneamento.risco_admissivel, ZarcZoneamento.grupo_risco)
            .where(
                and_(
                    ZarcZoneamento.municipio_ibge == dados.municipio_ibge,
                    ZarcZoneamento.cultura.ilike(dados.cultura),
                    ZarcZoneamento.decendio_plantio == decendio_proposto
                )
            )
        )
        resultado = await self.db.execute(query_zarc)
        regra_zarc = resultado.first()

        if not regra_zarc or float(regra_zarc.risco_admissivel) > 20.00:
            janelas_validas = await self._buscar_janelas_permitidas(dados.municipio_ibge, dados.cultura)
            periodo_errado = self._converter_decendio_para_texto(decendio_proposto)
            motivo = "Inconformidade de Risco" if regra_zarc else "Zoneamento Não Localizado"

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "erro_codigo": "ZARC_FORA_DA_JANELA",
                    "status_validacao": "INCONFORME",
                    "mensagem": f"{motivo} para a cultura {dados.cultura} no período de {periodo_errado} (Decêndio {decendio_proposto}) para este município.",
                    "sugestoes_janelas_plantio": janelas_validas
                }
            )

        return {
            "status_validacao": "CONFORME",
            "decendio_calculado": decendio_proposto,
            "risco_safra_pct": float(regra_zarc.risco_admissivel),
            "grupo_risco": regra_zarc.grupo_risco,
            "mensagem": "Planejamento Agronômico validado com sucesso junto aos parâmetros do ZARC/MAPA."
        }