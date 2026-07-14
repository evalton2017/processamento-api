import logging
from logging.handlers import RotatingFileHandler
import sys

def setup_logs():
    # 1. Definir o formato padrão do sistema
    log_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 2. Configurar o Handler do Arquivo Rotativo
    file_handler = RotatingFileHandler(
        "sistema.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(log_format)

    # 3. Configurar o Handler do Console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)

    # 4. Configurar o Logger Raiz (Root)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 5. CORREÇÃO: Permitir que os logs do Uvicorn propaguem nativamente para o Root
    # Em vez de sobrescrever handlers e formatadores internos, deixamos o log subir de nível
    for uvicorn_logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers = []      # Remove os handlers específicos do uvicorn
        uvicorn_logger.propagate = True   # Propaga a mensagem para o root_logger formatar corretamente
