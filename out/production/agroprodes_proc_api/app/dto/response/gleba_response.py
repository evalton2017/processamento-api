# app/dto/response/gleba_response.py ou dentro de produtor_router.py
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel

class RespostaGlebas(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    id_gleba: int
    id_produtor: int
    codigo_car: str = Field(..., example="BR-MG-3106200-1234567890ABCDEF12345")
    geometria: str = Field(..., example="POLYGON ((-44.41621163950453 -9.968400492342242))")
    area_hectares: float
    cultura_declarada: str = Field(..., example="Café")
    status_vmg: str = Field(..., example="CONFORME")
    conformidade_pct: float = Field(..., example=100.0)

    # CORREÇÃO CRÍTICA: Alterado de 'date' para 'str' para aceitar o texto formatado do serviço
    data_criacao: str = Field(..., example="20/06/2026")
    data_estimada_plantio: str = Field(..., example="05/01/2026")

class KpisResumoGlebas(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    total_cadastradas: int = Field(..., example=12)
    total_conformes: int = Field(..., example=9)
    total_em_analise: int = Field(..., example=2)
    total_alertas: int = Field(..., example=1)
    proxima_validacao: str = Field(..., example="15/07/2026")

class ItemTabelaGleba(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
    id_gleba: int
    codigo: str = Field(..., example="GLB-001")
    nome_gleba: str = Field(..., example="Fazenda Santa Clara")
    municipio: str = Field(..., example="Bom Jesus - PI")
    cultura_declarada: str = Field(..., example="Soja")
    area_ha: float = Field(..., example=120.50)
    status: str = Field(..., example="Conforme") # "Conforme", "Em analise", "Alerta"
    ultima_atualizacao: str = Field(..., example="12/06/2026 09:45")
    geometria: str # Texto WKT para visualização espacial rápida

class RespostaConsultaGlebasPainel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    kpis: KpisResumoGlebas
    glebas: List[ItemTabelaGleba]

class StatusPassosEsteira(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    geometria: str
    consulta_car: str
    ambiental: str
    cultura_ia: str
    zarc: str
    produtividade: str
    atestado: str

class BlocoPendencias(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    descricao: Optional[str] = None
    recomendacao: Optional[str] = None

class ItemHistoricoAtividade(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    descricao: str = Field(..., example="Atestado emitido com sucesso")
    data_hora: str = Field(..., example="12/06/2026 09:45")
    tipo: str = Field(..., example="sucesso") # "sucesso", "info", "alerta"


class DetalheBlocoZarc(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    portaria: str = Field(..., example="148, de 02/06/2025")
    grupo_de_risco: str = Field(..., example="Médio")
    risco_admissivel: str = Field(..., example="30%")
    janela_de_plantio: str = Field(..., example="01/10 a 20/11")
    sua_data_estimada: str = Field(..., example="15/12/2025")

class ResumoAnalisesCard(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    ambiental_status: str = Field(..., example="Conforme")
    ambiental_desc: str = Field(..., example="Sem conflitos ambientais")
    cultura_ia_status: str = Field(..., example="Condizente")
    cultura_ia_desc: str = Field(..., example="Soja (92% confiança)")
    produtividade_status: str = Field(..., example="Concluído")
    produtividade_desc: str = Field(..., example="72 sc/ha Estimativa média")
    atestado_status: str = Field(..., example="Emitido")
    atestado_desc: str = Field(..., example="Válido até 12/06/2027")

class RespostaLaudoDetalhadoGleba(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id_gleba: int
    id_produtor: int
    codigo: str = Field(..., example="GLB-001")
    codigo_car: str = Field(..., example="PI-2207702-XXXX")
    geometria: str
    area_ha: float
    cultura_declarada: str
    nome_gleba: str
    municipio: str
    status: str = Field(..., example="Conforme")
    ultima_atualizacao: str
    status_passos: StatusPassosEsteira
    ultimas_atividades: List[ItemHistoricoAtividade]
    informacoes_zarc: DetalheBlocoZarc
    resumo_analises: ResumoAnalisesCard