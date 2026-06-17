# app/models/notificacao_model.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.database.session import Base

class NotificacaoUsuarioModel(Base):
    __tablename__ = "notificacao_usuario"
    __table_args__ = {"schema": "agroprods"}

    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(255), nullable=False)

    status = Column(
        Enum(
            "PENDENTE", "LIDA", "ARQUIVADA",
            name="status_notificacao",
            schema="agroprods",
            inherit_schema=True
        ),
        nullable=False,
        server_default="PENDENTE"
    )

    tipo = Column(String(50), nullable=False)
    data_criacao = Column(DateTime, nullable=False, default=datetime.utcnow)
    data_atualizacao = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    id_gleba = Column(Integer, ForeignKey("agroprods.glebas.id_gleba", ondelete="CASCADE"), nullable=True)
    gleba = relationship("GlebaModel", back_populates="notificacoes")
