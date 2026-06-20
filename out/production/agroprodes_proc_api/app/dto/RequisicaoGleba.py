from pydantic import BaseModel
from typing import Optional

class RequisicaoGleba(BaseModel):
    id_produtor: int
    numero_car: str        # Vinculado ao campo codigo_car do banco
    geometria: str         # String WKT do polígono
    cultura_declarada: str # Ex: 'Soja'
    data_estimada_plantio: str # String no formato 'YYYY-MM-DD'
    area_hectares: float   # Área calculada dinamicamente pelo mapa
    codigo_municipio: int  # Código IBGE coletado no passo 2
    cpf_cnpj: str
    volume_declarado_comercializar: float
    data_estimada_colheita: str # String no formato 'YYYY-MM-DD'

    # Parâmetros de auditoria para o Ledger
    ip_origem: Optional[str] = "127.0.0.1"
    dispositivo_token: Optional[str] = "angular_ssr_client"
