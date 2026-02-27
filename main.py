"""FastAPI entrypoint -- Employee HR Service."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # Railway sets env vars natively

from config import API_KEY
from db import init_db
from routers import employees, exceptions, export, health, ingest

logger = logging.getLogger("hr.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not API_KEY:
        logger.warning("LOOMI_API_KEY not set -- all requests will be rejected")
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
app.include_router(exceptions.router, prefix="/exceptions")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
