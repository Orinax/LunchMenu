"""
FastAPI application entry point.

Endpoints:
    GET  /health   → { "ok": true }
    GET  /menu     → normalised weekly menu JSON (cached)
    POST /refresh  → force re-fetch (requires X-Refresh-Token header)
"""
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv  # type: ignore
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from cache import TTLCache  # noqa: E402  (after dotenv load)

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
REFRESH_TOKEN_SECRET = os.getenv("REFRESH_TOKEN_SECRET", "")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "21600"))

if not SPREADSHEET_ID:
    logger.warning("SPREADSHEET_ID env var is not set – /menu will fail until configured")

app = FastAPI(title="LunchMenu API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to extension origin in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_cache = TTLCache(ttl_seconds=CACHE_TTL)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/menu")
def get_menu():
    cached = _cache.get()
    if cached is not None:
        logger.debug("Returning cached menu data")
        return cached

    logger.info("Cache miss – fetching from Google Sheets")
    data = _fetch_menu()
    _cache.set(data)
    return data


@app.post("/refresh")
def refresh_menu(x_refresh_token: str = Header(default="")):
    if not REFRESH_TOKEN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="REFRESH_TOKEN_SECRET is not configured on this server.",
        )
    if x_refresh_token != REFRESH_TOKEN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Refresh-Token header.",
        )

    logger.info("Forced cache refresh triggered")
    _cache.invalidate()
    data = _fetch_menu()
    _cache.set(data)
    return {"ok": True, "refreshed": datetime.now(timezone.utc).isoformat()}


def _fetch_menu():
    if not SPREADSHEET_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SPREADSHEET_ID is not configured. Set the SPREADSHEET_ID environment variable.",
        )
    try:
        from sheets import fetch_and_parse

        return fetch_and_parse(SPREADSHEET_ID)
    except Exception as exc:
        logger.exception("Failed to fetch/parse spreadsheet: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch menu data: {exc}",
        )
