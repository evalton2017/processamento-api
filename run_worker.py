import sys
import asyncio

if sys.platform == "win32":
    # Define o seletor diretamente no loop atual em vez de alterar a política global
    asyncio.set_child_watcher(None) if hasattr(asyncio, "set_child_watcher") else None


if __name__ == "__main__":
    from taskiq.__main__ import main

    sys.argv = [
        "taskiq",
        "worker",
        "app.services.celery.celery_task:broker",
        "--workers", "1",
        "--log-level", "INFO"  # Ajustado de --loglevel para --log-level
    ]

    sys.exit(main())
