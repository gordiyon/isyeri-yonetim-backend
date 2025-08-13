# backend/main.py
import os
import asyncio
import logging
from typing import Optional

import asyncpg
from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

# Lokal geliştirmede .env yüklemek için (deploy'da zaten env var)
try:
    from dotenv import load_dotenv  # requirements.txt'te var
    load_dotenv()
except Exception:
    pass

logger = logging.getLogger("uvicorn")
app = FastAPI()

def ensure_sslmode(url: str) -> str:
    """DATABASE_URL içinde sslmode=require yoksa ekler."""
    if not url:
        return url
    lower = url.lower()
    if "sslmode=" in lower:
        return url
    # '?' var mı kontrol et, yoksa '?' ile ekle, varsa '&' ile ekle
    return f"{url}{'&' if '?' in url else '?'}sslmode=require"

DB_URL: Optional[str] = ensure_sslmode(os.getenv("DATABASE_URL", "").strip())

# Uygulama state: pool opsiyonel (DB down ise None kalabilir)
app.state.pool: Optional[asyncpg.Pool] = None

async def try_create_pool(retries: int = 3, delay: float = 2.0):
    """Pool'u oluşturmayı dener; başarısız olursa loglar ve tekrar dener."""
    global DB_URL
    if not DB_URL:
        logger.error("DATABASE_URL boş. Lütfen ortam değişkenini ayarlayın.")
        return None
    for i in range(1, retries + 1):
        try:
            pool = await asyncpg.create_pool(
                dsn=DB_URL,
                min_size=1,
                max_size=5,
                timeout=10,
            )
            logger.info("✅ PostgreSQL pool oluşturuldu.")
            return pool
        except Exception as e:
            logger.error(f"DB pool oluşturulamadı (deneme {i}/{retries}): {e}")
            if i < retries:
                await asyncio.sleep(delay)
    return None

@app.on_event("startup")
async def startup():
    # Başlangıçta dene; olmazsa uygulama ÇÖKMEYECEK, sonradan tekrar deneriz.
    app.state.pool = await try_create_pool()
    if app.state.pool is None:
        # Arka planda tekrar denemeye devam etsin (uygulama ayakta kalsın)
        async def background_retry():
            while app.state.pool is None:
                logger.info("DB bağlantısı başarısız, 10 sn sonra tekrar denenecek…")
                await asyncio.sleep(10)
                app.state.pool = await try_create_pool(retries=1, delay=0)
        asyncio.create_task(background_retry())

@app.on_event("shutdown")
async def shutdown():
    pool = app.state.pool
    if pool is not None:
        await pool.close()
        logger.info("PostgreSQL pool kapatıldı.")

@app.get("/health")
async def health():
    """Uygulama ayakta mı? (DB zorunlu değil)"""
    return {"ok": True, "db_connected": app.state.pool is not None}

@app.get("/db-ping")
async def db_ping():
    """DB’ye ulaşabiliyor muyuz?"""
    pool = app.state.pool
    if pool is None:
        raise HTTPException(status_code=503, detail="DB bağlantısı yok")
    try:
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1;")
        return {"ok": True, "result": val}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB hatası: {e}")

# Örnek kök endpoint
@app.get("/")
async def root():
    return {"status": "running"}
