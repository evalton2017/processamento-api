from datetime import date, datetime, timedelta
from fastapi import HTTPException, status

from app.repository.zarc_repository import ZarcRepository
from app.routers.produtor_router import ValidarZarcRequest

class ValidacaoZarcService:
    def __init__(self, zarc_repository: ZarcRepository):
        self.repository = zarc_repository

    def _calcular_decendio(self, data: date) -> int:
        dia = data.day
        mes = data.month
        decendio_mes = 1 if dia <= 10 else (2 if dia <= 20 else 3)
        return ((mes - 1) * 3) + decendio_mes

    def _converter_decendio_para_texto(self, decendio: int) -> str:
        if not decendio or decendio < 1 or decendio > 36:
            return f"Período Inválido (Decêndio informado: {decendio})"

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

    def _calcular_data_por_decendio(self, decendio: int, final: bool = False) -> date:
        """Converte um número de decêndio (1-36) em uma instância de date aproximada para o ano de 2026"""
        ano = 2026
        mes = ((decendio - 1) // 3) + 1
        posicao_mes = (decendio - 1) % 3

        if not final:
            dia = 1 if posicao_mes == 0 else (11 if posicao_mes == 1 else 21)
            return date(ano, mes, dia)
        else:
            if posicao_mes == 0:
                return date(ano, mes, 10)
            elif posicao_mes == 1:
                return date(ano, mes, 20)
            else:
                # Retorna o último dia do mês correspondente
                proximo_mes = mes + 1 if mes < 12 else 1
                proximo_ano = ano if mes < 12 else ano + 1
                ultimo_dia = (datetime(proximo_ano, proximo_mes, 1) - timedelta(days=1)).day
                return date(ano, mes, ultimo_dia)

    async def validar_planejamento_zarc(self, dados: ValidarZarcRequest) -> dict:
        """
        Valida o planejamento do produtor utilizando a parametrização dinâmica da tabela ZARC,
        garantindo sincronia total com as janelas sugeridas e exibidas no Front-end.
        """
        # 1. Validação lógica de consistência de datas
        data_plantio_pura = dados.dataEstimadaPlantio
        data_colheita_pura = dados.dataEstimadaColheita

        if data_colheita_pura <= data_plantio_pura:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A data estimada da colheita deve ser posterior à data de plantio."
            )

        # 2. Calcula o decêndio com base no input fornecido pelo usuário
        decendio_proposto = self._calcular_decendio(data_plantio_pura)

        # 3. 🌟 SINCRONIZAÇÃO: Consulta a tabela ZARC da mesma forma que a listagem geral
        registros = await self.repository.obter_calendario_zarc_municipio(dados.municipio_ibge, dados.cultura)

        if not registros:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "erro_codigo": "ZARC_FORA_DA_JANELA",
                    "status_validacao": "INCONFORME",
                    "mensagem": f"Zoneamento Não Localizado para a cultura {dados.cultura} nesta região."
                }
            )

        # 4. Agrupa os riscos mapeados por decêndio presentes na tabela oficial
        decendios_validos = {}
        regra_especifica_usuario = None

        for r in registros:
            # Captura a regra específica se bater com o decêndio que o usuário tentou forçar
            if r.decendio_plantio == decendio_proposto:
                regra_especifica_usuario = r

            # Alimenta o mapa de decêndios válidos com risco admissível <= 20%
            if float(r.risco_admissivel) <= 20.00:
                if r.decendio_plantio not in decendios_validos or float(r.risco_admissivel) < decendios_validos[r.decendio_plantio]:
                    decendios_validos[r.decendio_plantio] = float(r.risco_admissivel)

        # 5. 🌟 CRITERIO DE VALIDAÇÃO: Verifica se o decêndio proposto atende ao critério de corte (< 20%)
        if decendio_proposto not in decendios_validos:
            periodo_errado = self._converter_decendio_para_texto(decendio_proposto)
            motivo = "Inconformidade de Risco" if regra_especifica_usuario else "Zoneamento Não Localizado"

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "erro_codigo": "ZARC_FORA_DA_JANELA",
                    "status_validacao": "INCONFORME",
                    "mensagem": f"{motivo} para a cultura {dados.cultura} (Safra {dados.safra}) no período de {periodo_errado} (Decêndio {decendio_proposto}) para este município."
                }
            )

        # 6. Retorno de sucesso casado com o comportamento esperado pelo Angular Material Stepper
        risco_final = decendios_validos[decendio_proposto]
        grupo_risco_final = regra_especifica_usuario.grupo_risco if regra_especifica_usuario else "RISCO_20"

        return {
            "status_validacao": "CONFORME",
            "decendio_calculado": decendio_proposto,
            "risco_safra_pct": risco_final,
            "grupo_risco": grupo_risco_final,
            "mensagem": f"Planejamento Agronômico validado com sucesso para a Safra {dados.safra} junto aos parâmetros do ZARC/MAPA."
        }

    async def consultar_janela_geral_zarc(self, municipio_ibge: int, cultura: str) -> dict:
        """
        Busca os registros reais do repositório, calcula as datas operacionais
        e devolve o painel de sugestões montado dinamicamente do banco de dados.
        """
        registros = await self.repository.obter_calendario_zarc_municipio(municipio_ibge, cultura)

        if not registros:
            raise HTTPException(
                status_code=404,
                detail=f"Zoneamento ZARC não parametrizado ou indisponível para a cultura '{cultura}' nesta região."
            )

        # Filtra e agrupa para evitar duplicidade de decêndios se houver múltiplos tipos de solo cadastrados
        decendios_mapeados = {}
        for r in registros:
            d = r.decendio_plantio
            risco = float(r.risco_admissivel)
            # Mantém apenas o menor risco do decêndio caso haja repetição por tipo de solo
            if d not in decendios_mapeados or risco < decendios_mapeados[d]:
                decendios_mapeados[d] = risco

        # Ordena as chaves dos decêndios obtidos
        decendios_ordenados = sorted(decendios_mapeados.keys())

        # Monta a lista de sugestões tipada
        sugestoes = [
            {
                "decendio": d,
                "periodo_sugerido": self._converter_decendio_para_texto(d),
                "risco_pct": int(decendios_mapeados[d])
            }
            for d in decendios_ordenados if decendios_mapeados[d] <= 20.00 # Mantém o filtro de segurança de risco máximo de 20%
        ]

        # Calcula dinamicamente os limites de calendário com base no primeiro e último decêndios encontrados
        data_inicio = self._calcular_data_por_decendio(decendios_ordenados[0], final=False)
        data_fim = self._calcular_data_por_decendio(decendios_ordenados[-1], final=True)

        return {
            "cultura": cultura,
            "municipio_ibge": municipio_ibge,
            "data_inicio_permitida": data_inicio,
            "data_fim_permitida": data_fim,
            "sugestoes_janelas_plantio": sugestoes,
            "mensagem_auxiliar": f"Calendário agrícola extraído dinamicamente das portarias oficiais do MAPA para o município {municipio_ibge}."
        }
