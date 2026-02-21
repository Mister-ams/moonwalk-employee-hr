"""FastAPI entrypoint — Employee HR Service."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # Railway sets env vars natively

from config import API_KEY
from db import init_db
from routers import employees, export, health, ingest

logger = logging.getLogger("hr.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not API_KEY:
        logger.warning("HR_API_KEY not set — all requests will be rejected")
    init_db()
    yield


app = FastAPI(title="Employee HR Service", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.appsmith.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

app.include_router(health.router)
app.include_router(employees.router, prefix="/employees")
app.include_router(ingest.router, prefix="/ingest")
app.include_router(export.router, prefix="/export/csv")
