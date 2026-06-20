from datetime import datetime, date
from fastapi import HTTPException, status
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.dto.RequisicaoGleba import RequisicaoGleba
from app.repository.gleba_repository import GlebaRepository
from app.services.celery.celery_task import executar_pipeline


class GlebaService:
    def __init__(self, db: AsyncSession):
        self.repo = GlebaRepository(db)
        self.db = db

    async def cadastrar_gleba(self, dados: RequisicaoGleba) -> Dict[str, Any]:
        try:
            # Garante a atomicidade da operação utilizando o bloco begin da sessão externa
            async with self.db.begin():
                # 1. Atualização do Produtor
                pessoa = await self.repo.obter_pessoa_por_id(dados.id_produtor)
                if not pessoa:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Produtor (Pessoa) não encontrado no sistema."
                    )
                pessoa.cpf_cnpj = dados.cpf_cnpj

                # 2. Validação do CAR
                propriedade = await self.repo.verificar_propriedade_car(dados.numero_car)
                if not propriedade:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Propriedade não encontrada."
                    )

                # 3. Conversão de data e salvamento da Gleba
                data_plantio = datetime.strptime(dados.data_estimada_plantio, "%Y-%m-%d")
                data_estimada_colheita = datetime.strptime(dados.data_estimada_colheita, "%Y-%m-%d")
                nova_gleba = await self.repo.salvar_gleba(dados, data_plantio,data_estimada_colheita)


                # 4. Salvar Consentimento LGPD
                ip = dados.ip_origem or "127.0.0.1"
                token = dados.dispositivo_token or "token_angular_2026"
                await self.repo.salvar_consentimento(dados.id_produtor, ip, token, nova_gleba.id_gleba)

            # 5. Disparo do pipeline assíncrono (Fora do bloco de transação do banco)
            await executar_pipeline.kiq(
                id_gleba=nova_gleba.id_gleba,
                cultura_declarada=dados.cultura_declarada,
                id_produtor=dados.id_produtor
            )

            return {
                "status": "SUCESSO",
                "mensagem": "Dados persistidos e cadastro do produtor atualizado com sucesso de forma atômica.",
                "id_gleba_gerado": nova_gleba.id_gleba,
                "area_validada_hectares": float(nova_gleba.area_hectares),
                "produtor_atualizado": pessoa.nome
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro na transação atômica multischema: {str(e)}",
            )

    async def obter_gleba(self, id_contrato: int) -> Dict[str, Any]:
        try:
            gleba = await self.repo.obter_gleba_por_id(id_contrato)
            if not gleba:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Gleba agrícola não encontrada no sistema.",
                )
            return self._formatar_resposta_gleba(gleba)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao recuperar dados da gleba: {str(e)}",
            )

    async def listar_glebas_por_produtor(self, id_produtor: int) -> list:
        dados_brutos = await self.repo.listar_glebas_com_conformidade_auditada(id_produtor)

        lista_formatada = []
        for r in dados_brutos:
            lista_formatada.append({
                "id_gleba": r.id_gleba,
                "id_produtor": r.id_produtor,
                "codigo_car": r.codigo_car,
                "geometria": r.geometria,
                "area_hectares": float(r.area_hectares),
                "data_criacao": r.data_criacao.strftime("%d/%m/%Y") if isinstance(r.data_criacao, datetime) else "",
                "data_estimada_plantio": r.data_estimada_plantio.strftime("%d/%m/%Y") if isinstance(r.data_estimada_plantio, datetime) else "",
                "cultura_declarada": r.cultura_declarada if r.cultura_declarada else "Não Declarada",
                "status_vmg": r.status_vmg,
                "conformidade_pct": float(r.conformidade_pct)
            })

        return lista_formatada

    def _formatar_resposta_gleba(self, gleba: Any) -> Dict[str, Any]:
        """Método auxiliar para mapear a linha do banco para a estrutura de dicionário."""
        return {
            "id_gleba": gleba.id_gleba,
            "id_produtor": gleba.id_produtor,
            "codigo_car": gleba.codigo_car,
            "geometria": gleba.geometria,
            "area_hectares": float(gleba.area_hectares),
            "data_criacao": gleba.data_criacao.date() if hasattr(gleba.data_criacao, 'date') else gleba.data_criacao,
            "cultura_declarada": gleba.cultura_declarada,
            "data_estimada_plantio": gleba.data_estimada_plantio.date() if hasattr(gleba.data_estimada_plantio, 'date') else gleba.data_estimada_plantio,
            "codigo_municipio": gleba.codigo_municipio
        }

    def calcular_decendio_da_data(self, data_alvo: date) -> int:
        """Calcula matematicamente o decêndio do ano civil (1 a 36)"""
        mes = data_alvo.month
        dia = data_alvo.day
        decendio_base = (mes - 1) * 3

        if dia <= 10:
            return decendio_base + 1
        elif dia <= 20:
            return decendio_base + 2
        else:
            return decendio_base + 3

    def validar_planejamento_agricola(self, municipio_ibge: int, cultura: str, data_plantio: date) -> Dict[str, Any]:
        """
        Orquestra a regra de negócio do ZARC cruzando o calendário com o banco de dados.
        """
        # 1. Calcula o decêndio da data escolhida pelo produtor
        decendio_usuario = self.calcular_decendio_da_data(data_plantio)

        # 2. Consulta o repositório para checar a tabela zarc_zoneamento
        registros = self.repository.buscar_registros_por_decendio(municipio_ibge, cultura, decendio_usuario)

        # 3. Regra de Decisão Agroclimática
        if not registros:
            return {
                "status_validacao": "INCONFORME",
                "mensagem": (
                    f"A data de plantio ({data_plantio.strftime('%d/%m/%Y')}) corresponde ao decêndio {decendio_usuario}. "
                    f"Este período não possui zoneamento permitido ou apresenta risco climático superior a 40% "
                    f"para a cultura de {cultura} neste município."
                )
            }

        # Caso encontre registros validos, extrai o menor risco dos solos mapeados
        menor_risco_encontrado = min([r.risco_admissivel for r in registros])

        return {
            "status_validacao": "CONFORME",
            "mensagem": (
                f"Operação validada! O plantio no decêndio {decendio_usuario} está em conformidade com as "
                f"diretrizes da tabela oficial do ZARC, apresentando risco de {menor_risco_encontrado}% para a cultura de {cultura}."
            )
        }