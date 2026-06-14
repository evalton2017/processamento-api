from datetime import date

from pydantic import BaseModel, Field, field_serializer


class RespostaGlebas(BaseModel):
    id_gleba: int
    id_produtor: int
    codigo_car :  str = Field(..., example="BR-MG-3106200-1234567890ABCDEF12345")
    geometria:  str = Field(..., example="POLYGON ((-44.41621163950453 -9.968400492342242)")
    area_hectares :float
    data_criacao: date = Field(..., examples=["2026-10-05"])
    data_estimada_plantio: date = Field(..., examples=["2026-12-10"])
    cultura_declarada:  str = Field(..., example="Cefe")

    # Serializador para formatar a data_criacao como dd/mm/yyyy
    @field_serializer('data_criacao')
    def serialize_data_criacao(self, dt: date, _info):
        return dt.strftime('%d/%m/%Y')

    # Serializador para formatar a data_estimada_plantio como dd/mm/yyyy
    @field_serializer('data_estimada_plantio')
    def serialize_data_plantio(self, dt: date, _info):
        return dt.strftime('%d/%m/%Y')