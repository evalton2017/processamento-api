from pydantic import BaseModel
from typing import List, Optional

class FiltrosGlebaAvancadoDTO(BaseModel):
    safra: str = "2025/2026"
    municipio: Optional[str] = "Todos"
    cultura: Optional[str] = "Todos"
    status_gleba: Optional[str] = "Todos"
    conformidade_ambiental: Optional[str] = "Todos"
    cpf_cnpj: Optional[str] = None
    car: Optional[str] = None
    ordenar_por: Optional[str] = "Mais recentes"

class GlebaLinhaNovoModeloDTO(BaseModel):
    car: str
    produtor: str
    municipio: str
    cultura: str
    area_ha: float
    safra: str
    conformidade_ambiental: str
    status_gleba: str
    atualizacao: str

class RespostaTabelaGlebasNovaDTO(BaseModel):
    total_registros: int
    pagina_atual: int
    total_paginas: int
    dados: List[GlebaLinhaNovoModeloDTO]
