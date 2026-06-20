from pydantic import BaseModel, Field

class MunicipioResponse(BaseModel):
    codigo_municipio: int = Field(..., description="Código do município no IBGE", example=3550308)
    nome_municipio: str = Field(..., description="Nome do município", example="São Paulo")
    sigla_uf: str = Field(..., description="Sigla do estado (UF)", example="SP")
    estado: str = Field(..., description="Nome completo do estado", example="São Paulo")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "codigo_municipio": 3550308,
                "nome_municipio": "São Paulo",
                "sigla_uf": "SP",
                "estado": "São Paulo"
            }
        }
    }
