from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, asyncpg
from dotenv import load_dotenv

load_dotenv()  # .env dosyasını oku

app = FastAPI()
DB_URL = os.getenv("DATABASE_URL")  # Supabase Postgres bağlantısı

class CariMainIn(BaseModel):
    kod: str
    ad: str
    tip: str
    telefon: str | None = None
    il: str | None = None
    ilce: str | None = None

@app.on_event("startup")
async def startup():
    app.state.pool = await asyncpg.create_pool(dsn=DB_URL)

@app.post("/cari/main")
async def create_main(c: CariMainIn):
    q = """insert into cari_main(kod, ad, tip, telefon, il, ilce)
           values($1,$2,$3,$4,$5,$6) returning id"""
    try:
        async with app.state.pool.acquire() as con:
            rid = await con.fetchval(q, c.kod, c.ad, c.tip, c.telefon, c.il, c.ilce)
            return {"id": str(rid)}
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Aynı kayıt zaten var")
