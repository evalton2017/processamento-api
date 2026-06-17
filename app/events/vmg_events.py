import asyncio
from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notificacao_model import NotificacaoUsuarioModel

@dataclass
class EventoAnaliseConcluida:
    """Carrega todos os dados gerados pelo pipeline para processamento de eventos."""
    id_produtor: int
    id_gleba: int
    cultura_declarada: str
    cultura_identificada: str
    confianca: float
    produtividade: float
    bloqueio_ambiental: bool

class GerenciadorEventosVMG:
    def __init__(self):
        self._ouvintes: List[Callable[[EventoAnaliseConcluida, AsyncSession], Awaitable[None]]] = []

    def registrar_ouvinte(self, ouvinte: Callable[[EventoAnaliseConcluida, AsyncSession], Awaitable[None]]):
        self._ouvintes.append(ouvinte)

    async def disparar(self, evento: EventoAnaliseConcluida, db_session: AsyncSession):
        """Dispara o evento para todos os ouvintes registrados em paralelo."""
        if not self._ouvintes:
            return
        # Executa todos os listeners concorrentemente dentro da mesma transação
        await asyncio.gather(*(ouvinte(evento, db_session) for ouvinte in self._ouvintes))


# ==============================================================================
# OUVINTE (LISTENER) - REGRAS DE NOTIFICAÇÃO DA PORTARIA
# ==============================================================================
async def ouvinte_gerador_notificacoes(evento: EventoAnaliseConcluida, db_session: AsyncSession):
    """
    Interpreta os resultados do evento e insere as notificações na sessão
    respeitando estritamente o modelo físico do banco de dados (schema: agroprods).
    """

    # Regra 1: Bloqueio Socioambiental Detectado (Itens 2 e 2.1)
    if evento.bloqueio_ambiental:
        db_session.add(NotificacaoUsuarioModel(
            usuario=str(evento.id_produtor),     # 🟢 CORREÇÃO: Mapeado para a coluna 'usuario' (String)
            tipo="COMPLIANCE_BLOQUEIO",          # 🟢 CORREÇÃO: Alinhado com a coluna 'tipo'
            status="PENDENTE",                   # status padrão exigido
            id_gleba=evento.id_gleba             # 🟢 RASTREABILIDADE: Vincula à chave estrangeira física
        ))

    # Regra 2: Divergência Crítica de Cultura por IA (Item 3.6-a)
    if evento.cultura_identificada.upper() != evento.cultura_declarada.upper():
        db_session.add(NotificacaoUsuarioModel(
            usuario=str(evento.id_produtor),
            tipo="IA_DIVERGENCIA",
            status="PENDENTE",
            id_gleba=evento.id_gleba
        ))

    # Regra 3: Sucesso da Operação Sem Alertas
    if not evento.bloqueio_ambiental and evento.cultura_identificada.upper() == evento.cultura_declarada.upper():
        db_session.add(NotificacaoUsuarioModel(
            usuario=str(evento.id_produtor),
            tipo="PIPELINE_SUCESSO",
            status="PENDENTE",
            id_gleba=evento.id_gleba
        ))

# Instância global configurada para o ecossistema
vmg_event_dispatcher = GerenciadorEventosVMG()
vmg_event_dispatcher.registrar_ouvinte(ouvinte_gerador_notificacoes)
