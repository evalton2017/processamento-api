from datetime import datetime
from pydantic import BaseModel

class EventoClimaticoResponse(BaseModel):
    evento: str
    municipio: str
    data: datetime
    impacto: str
    glebas_afetadas: int

    class Config:
        from_attributes = True
