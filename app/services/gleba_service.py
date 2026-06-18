from datetime import datetime
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
                nova_gleba = await self.repo.salvar_gleba(dados, data_plantio)

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

    async def listar_glebas_por_produtor(self, id_produtor: int) -> List[Dict[str, Any]]:
        try:
            linhas = await self.repo.obter_glebas_por_produtor(id_produtor)
            return [self._formatar_resposta_gleba(g) for g in linhas]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao recuperar a listagem de glebas: {str(e)}",
            )

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
