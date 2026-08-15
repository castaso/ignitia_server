"""Run the dev server:  python run.py

Host/port come from environment or .env (defaults 0.0.0.0:86, the port the
Flutter client points at).
"""

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
