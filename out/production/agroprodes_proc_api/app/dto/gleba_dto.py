from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional
from decimal import Decimal

class GlebaCreateInput(BaseModel):
    # Passo 1: Dados Gerais
    nome_gleba: str = Field(..., max_length=150, description="Ex: Fazenda Boa Vista")
    id_produtor: int = Field(..., description="ID interno do Produtor")
    id_car_vinculado: str = Field(..., description="CAR Selecionado no input de busca")
    matricula_transcricao: Optional[str] = Field(None, max_length=100, description="Número da matrícula da terra")

    # Passo 2: Localização (Campos calculados ou selecionados automaticamente)
    codigo_municipio: int = Field(..., description="Código IBGE do município (Bom Jesus)")
    bacia_hidrografica: Optional[str] = Field(None, max_length=150, description="Ex: Bacia do Parnaíba")
    bioma: Optional[str] = Field(None, max_length=50, description="Ex: Cerrado")
    regiao_planejamento: Optional[str] = Field(None, max_length=100, description="Ex: Sul Piauiense")
    latitude_centroide: Decimal = Field(..., max_digits=10, decimal_places=6)
    longitude_centroide: Decimal = Field(..., max_digits=10, decimal_places=6)

    # Passo 3: Delimitação da Gleba (Desenhado no Mapa)
    geometria: str = Field(..., description="Formato WKT do polígono desenhado no mapa")
    area_hectares: Decimal = Field(..., max_digits=10, decimal_places=2, description="Área calculada automaticamente (101,95 ha)")
    perimetro_metros: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2, description="Perímetro calculado (4.512,05 m)")

    # Passo 4: Informações Agrícolas
    cultura_declarada: str = Field(..., max_length=100, description="Cultura Principal (Soja)")
    safra: str = Field(..., max_length=20, description="Safra selecionada (2024/2025)")
    data_estimada_plantio: Optional[date] = Field(None, description="Data estimada do Plantio (15/10/2024)")
    data_estimada_colheita: Optional[date] = Field(None, description="Data estimada da Colheita (15/02/2025)")
    historico_producao_anterior: Optional[str] = Field(None, description="Histórico de produção da área")


class GlebaResponse(BaseModel):
    id_gleba: int
    nome_gleba: str
    id_produtor: int
    codigo_car: str
    area_hectares: Decimal
    cultura_declarada: str
    safra: str
    status: str = Field("Em Validação", description="Status inicial padrão exibido no protótipo")
    data_criacao: datetime

    class Config:
        from_attributes = True
