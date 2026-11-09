"""FastAPI application entrypoint for QueryTrellis Studio."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import academy, ai, context, debug, nl2sql, optimize, sql
from src.api.state import get_container

load_dotenv(override=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    container = get_container()
    container.ensure_assets()
    yield
    container.context_manager.connector.disconnect_live()


app = FastAPI(
    title="QueryTrellis Studio API",
    version="2.0.0",
    description="Natural Language SQL Development, Debugging, Optimization & Visual Learning Backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(context.router)
app.include_router(nl2sql.router)
app.include_router(sql.router)
app.include_router(debug.router)
app.include_router(optimize.router)
app.include_router(academy.router)
app.include_router(ai.router)


@app.get("/api/health")
def health_check():
    c = get_container()
    snap = c.context_manager.get_snapshot()
    return {
        "status": "ok",
        "active_database": snap.label,
        "engine": snap.engine,
        "dialect": snap.dialect,
        "table_count": len(snap.tables),
        "ai_provider": c.ai_manager.config.active_provider,
    }


def main() -> None:
    import uvicorn

    host = os.getenv("QT_API_HOST", "127.0.0.1")
    port = int(os.getenv("QT_API_PORT", "8000"))
    uvicorn.run("src.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
