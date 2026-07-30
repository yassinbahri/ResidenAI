from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import router
from app.core.config import get_settings
from app.core.db import SessionLocal

app = FastAPI(title="Residency Tracker API (internal only)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().dashboard_origins,
    allow_methods=["GET"],
    allow_headers=["X-Admin-Token", "Content-Type"],
)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
