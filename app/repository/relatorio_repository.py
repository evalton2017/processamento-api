# app/repositories/relatorio_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional

class RelatorioRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def obter_dados_consolidados_atestado(self, id_atestado: int) -> Optional[dict]:
        """
        Executa uma query agregada trazendo dados das tabelas de auditoria (ledger)
        e cruzando de forma otimizada com o schema de produçao.
        """
        query = text("""
                     SELECT
                         -- Cabeçalho & Gleba
                         g.nome_gleba,
                         d_led.cultura_declarada AS cultura_principal,
                         ia_led.safra,
                         atl.data_emissao,
                         atl.status_validacao,
                         g.area_hectares,

                         -- Resumo Conformidade (Ledgers de Auditoria)
                         laudo_led.conflito_socioambiental,
                         laudo_led.conflito_prodes,
                         laudo_led.conflito_ibama_icmbio,
                         laudo_led.conflito_comunidades,
                         ia_led.status_conducao,
                         d_led.possui_certificado_bpa,
                         d_led.decendio_plantio_zarc,
                         d_led.risco_zarc_admissivel,

                         -- Informações da Gleba
                         m.nome_municipio || ' / ' || m.sigla_uf AS municipio_uf,
                         g.codigo_car,
                         g.geometria::text AS coordenadas_raw, -- Tratado posteriormente como centróide
                         g.data_criacao AS data_cadastro_gleba,

                         -- Produtividade (Transacional vs IA)
                         ia_prod_led.volume_comercializar_declarado,
                         ia_prod_led.produtividade_ia_sacas_ha,
                         atl.estimativa_produtividade_sacas,

                         -- Metadados de Autenticidade
                         atl.id_atestado,
                         atl.hash_relatorio,
                         d_led.data_estimada_plantio,
                         d_led.data_estimada_colheita

                     FROM audit.atestados_vmg_ledger atl
                              JOIN agroprods.glebas g ON g.id_gleba = atl.id_gleba
                              LEFT JOIN agroprods.municipio_ibge m ON m.codigo_municipio = g.codigo_municipio

                         -- Cruzamento com as últimas fotos imutáveis de auditoria
                              LEFT JOIN audit.declaracao_gleba_periodo_ledger d_led
                                        ON d_led.id_gleba = g.id_gleba
                     ORDER BY d_led.data_registro DESC LIMIT 1
                
            LEFT JOIN audit.ia_classificacao_cultura_ledger ia_led
                     ON ia_led.id_gleba = g.id_gleba
                     ORDER BY ia_led.data_analise DESC LIMIT 1

                         LEFT JOIN audit.historico_laudos_ambientais_ledger laudo_led
                     ON laudo_led.id_gleba = g.id_gleba
                     ORDER BY laudo_led.data_auditoria DESC LIMIT 1

                         LEFT JOIN audit.ia_estimativa_produtividade_ledger ia_prod_led
                     ON ia_prod_led.id_gleba = g.id_gleba
                     ORDER BY ia_prod_led.data_calculo DESC LIMIT 1

                     WHERE atl.id_atestado = :id_atestado
                     """)

        result = await self.db.execute(query, {"id_atestado": id_atestado})
        row = result.mappings().first()
        return dict(row) if row else None
