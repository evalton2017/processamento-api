# app/dto/response/gleba_response.py ou dentro de produtor_router.py
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
