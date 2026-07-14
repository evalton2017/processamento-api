from pydantic import BaseModel, Field

class MunicipioIbgeSchema(BaseModel):
    codigo_municipio: int = Field(..., alias="codigo_municipio")
    nome_municipio: str
    codigo_uf: int
    sigla_uf: str = Field(..., max_length=2, description="Ex: MT, BA")
    estado: str
    latitude: float
    longitude: float
    ddd: int

    class Config:
        populate_by_name = True
        from_attributes = True
