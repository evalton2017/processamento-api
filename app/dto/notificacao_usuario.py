from pydantic import BaseModel, Field
from datetime import datetime


class NotificacaoUsuario(BaseModel):
    id: int
    id_gleba: int = Field(..., description="Chave estrangeira identificada no diagrama de relacionamentos")
    usuario: str
    status: str = Field(..., description="Ex: Lida, Não Lida")
    tipo: str = Field(..., description="Ex: Alerta de Desmatamento, Sucesso IA")
    data_criacao: datetime
    data_atualizacao: datetime

    class Config:
        from_attributes = True