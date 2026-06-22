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

    def _calcular_data_por_decendio(self, decendio: int, ano_base: int, final: bool = False) -> str:
        """
        Calcula a data exata de um decêndio (1 a 36) projetada no ano real da safra.
        """
        # Cada mês possui exatamente 3 decêndios no ZARC
        mes = ((decendio - 1) // 3) + 1
        posicao_decendio_no_mes = ((decendio - 1) % 3) + 1

        # Regra de cruzamento de ano da Safra Brasileira (Ex: Safra 2026/2027):
        # Os decêndios de 1 a 18 (Janeiro a Junho) acontecem no segundo ano do ciclo (2027)
        # Os decêndios de 19 a 36 (Julho a Dezembro) acontecem no primeiro ano do ciclo (2026)
        if decendio <= 18:
            ano_real = ano_base + 1
        else:
            ano_real = ano_base

        # Define o dia com base na posição do decêndio dentro do mês correspondente
        if not final:
            # Data de início do decêndio (Dias 1, 11 ou 21)
            dia = 1 if posicao_decendio_no_mes == 1 else (11 if posicao_decendio_no_mes == 2 else 21)
        else:
            # Data de término do decêndio (Dias 10, 20 ou o último dia do mês corrente)
            if posicao_decendio_no_mes == 1:
                dia = 10
            elif posicao_decendio_no_mes == 2:
                dia = 20
            else:
                # Caso seja o terceiro decêndio, calcula o último dia do mês de forma dinâmica
                if mes == 2:
                    # Trata ano bissexto para o mês de Fevereiro
                    is_bissexto = (ano_real % 4 == 0 and ano_real % 100 != 0) or (ano_real % 400 == 0)
                    dia = 29 if is_bissexto else 28
                elif mes in (4, 6, 9, 11):
                    dia = 30
                else:
                    dia = 31

        return date(ano_real, mes, dia)

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

    async def consultar_janela_geral_zarc(self, municipio_ibge: int, cultura: str, safra: str) -> dict:
        """
        Busca os registros reais do repositório, calcula as datas operacionais
        baseando-se no ano de vigência da safra informada.
        """
        registros = await self.repository.obter_calendario_zarc_municipio(municipio_ibge, cultura)

        if not registros:
            raise HTTPException(
                status_code=404,
                detail=f"Zoneamento ZARC não parametrizado para a cultura '{cultura}' nesta região."
            )

        decendios_mapeados = {}
        for r in registros:
            d = r.decendio_plantio
            risco = float(r.risco_admissivel)
            if d not in decendios_mapeados or risco < decendios_mapeados[d]:
                decendios_mapeados[d] = risco

        decendios_ordenados = sorted(decendios_mapeados.keys())

        sugestoes = [
            {
                "decendio": d,
                "periodo_sugerido": self._converter_decendio_para_texto(d),
                "risco_pct": int(decendios_mapeados[d])
            }
            for d in decendios_ordenados if decendios_mapeados[d] <= 20.00
        ]

        if not sugestoes:
            raise HTTPException(
                status_code=400,
                detail="Nenhuma janela atende ao limite de risco de 20% para esta cultura na região."
            )

        # 🟢 EXTRAÇÃO DO ANO BASE DA SAFRA (Limpa textos se houver, ex: "Safra 2026/2027" -> 2026)
        numeros_safra = ''.join(c for c in safra if c.isdigit() or c == '/')
        ano_base_str = numeros_safra.split('/')[0]
        ano_base_safra = int(ano_base_str)

        # Filtra os decendios estritamente válidos pelo risco
        decendios_validos = [s["decendio"] for s in sugestoes]

        # 🟢 CORREÇÃO DAS DATAS: Passando o ano base correto extraído da safra
        data_inicio = self._calcular_data_por_decendio(decendios_validos[0], ano_base=ano_base_safra, final=False)
        data_fim = self._calcular_data_por_decendio(decendios_validos[-1], ano_base=ano_base_safra, final=True)

        return {
            "cultura": cultura,
            "municipio_ibge": municipio_ibge,
            "safra_vigente": safra,
            "data_inicio_permitida": data_inicio,
            "data_fim_permitida": data_fim,
            "sugestoes_janelas_plantio": sugestoes,
            "mensagem_auxiliar": f"Calendário agrícola extraído e projetado para o ciclo da safra {safra}."
        }
