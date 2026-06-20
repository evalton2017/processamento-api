# app/dto/PlanejamentoAgronomicoDTO.py
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel
from datetime import date

class PlanejamentoAgronomicoDTO(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    municipio_ibge: int = Field(..., description="Código IBGE")
    cultura: str = Field(..., description="Cultura")
    safra: str = Field(..., description="Safra")
    volume_declarado_comercializar: float = Field(..., description="Volume")

    # CONFIRA ESTAS DUAS EXPRESSÕES ABAIXO (LETRA POR LETRA):
    data_estimada_plantio: date = Field(..., description="Data de Plantio")
    data_estimada_colheita: date = Field(..., description="Data de Colheita")
