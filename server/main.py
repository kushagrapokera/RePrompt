import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.insert(0, ".")

from pipeline import RePrompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reprompt-server")

rp: RePrompt | None = None
_ready: bool = False
_log_path: str = os.path.join(os.path.dirname(__file__), "..", "query_log.jsonl")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rp
    logger.info("Starting RePrompt server ...")
    rp = RePrompt()
    yield
    rp = None
    logger.info("RePrompt server stopped.")


app = FastAPI(title="RePrompt API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EnhanceRequest(BaseModel):
    query: str


class EnhanceResponse(BaseModel):
    original: str
    cleaned: str
    intent: str
    confidence: float
    enhanced: str | None


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": rp is not None}


@app.post("/enhance", response_model=EnhanceResponse)
async def enhance(req: EnhanceRequest):
    if rp is None:
        raise HTTPException(503, "Server not ready (models still loading)")
    if not req.query.strip():
        raise HTTPException(422, "Query cannot be empty")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, rp.run, req.query)
    except Exception as e:
        logger.exception("Enhancement failed")
        raise HTTPException(500, f"Enhancement failed: {e}")

    # Log query history
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original": result["original"],
            "intent": result["intent"],
            "confidence": result["confidence"],
            "lfm_intent": result.get("lfm_intent"),
            "lfm_confidence": result.get("lfm_confidence"),
            "used_fallback": result.get("used_fallback", False),
            "distilbert_intent": result.get("distilbert_intent"),
            "distilbert_confidence": result.get("distilbert_confidence"),
            "enhanced": result["enhanced"],
        }
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Don't break the request for logging

    return EnhanceResponse(**result)
