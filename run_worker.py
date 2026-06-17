import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import app.models.gleba_model
import app.models.models_ledger

if __name__ == "__main__":
    from taskiq.__main__ import main
    sys.argv = [
        "taskiq",
        "worker",
        "app.services.celery.celery_task:broker",
        "--workers", "1",
        "--log-level", "INFO"
    ]
    sys.exit(main())
