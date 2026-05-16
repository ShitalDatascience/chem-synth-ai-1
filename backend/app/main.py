from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import WebSocket
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

from app.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="ChemSynth AI Backend",
        version="0.1.0",
        description=(
            "Agentic RAG service for drug discovery over "
            "ChEMBL + DeepChem + ChemLLM."
        ),
    )

    # -----------------------------
    # CORS CONFIG
    # -----------------------------
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------
    # API ROUTES
    # -----------------------------
    app.include_router(api_router)

    # -----------------------------
    # WEBSOCKET (dev echo)
    # -----------------------------
    @app.websocket("/api/ws/chat")
    async def chat_ws(websocket: WebSocket):
        await websocket.accept()
        print("[WS] connection accepted")

        while True:
            data = await websocket.receive_text()
            print("[WS] received:", data)
            await websocket.send_text(f"echo: {data}")

    # -----------------------------
    # STARTUP EVENT
    # -----------------------------
    @app.on_event("startup")
    async def _startup():
        logger.info("ChemSynth AI backend started")
        try:
            from app.services.lora_report_service import log_lora_startup_status

            log_lora_startup_status()
        except Exception as exc:
            logger.warning("LoRA startup probe skipped: %s", exc)

    return app


# -----------------------------
# FASTAPI APP INSTANCE
# -----------------------------
app = create_app()