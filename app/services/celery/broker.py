import os
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

REDIS_URL = os.getenv("REDIS_URL", "redis://:duke2214@127.0.0.1:6379/0")

# Dicionário com configurações para evitar o timeout de leitura
redis_kwargs = {
    "socket_timeout": None,          # Desativa o timeout de leitura do socket
    "socket_keepalive": True,        # Mantém a conexão ativa com o servidor
    "health_check_interval": 30       # Verifica se a conexão caiu a cada 30 segundos
}

# Configura o backend com os novos parâmetros
result_backend = RedisAsyncResultBackend(
    REDIS_URL,
    **redis_kwargs
)

# Inicializa o broker passando as configurações adicionais
broker = ListQueueBroker(
    REDIS_URL,
    **redis_kwargs
).with_result_backend(result_backend)
