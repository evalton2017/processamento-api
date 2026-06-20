from pydantic import BaseModel
from datetime import datetime


class TimelineEvento(BaseModel):
    id: int
    data_evento: datetime
    tipo: str
    titulo: str
    descricao: str
    status: str | None = None
    id_gleba: int | None = None

    class Config:
        from_attributes = True