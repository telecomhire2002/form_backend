import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

load_dotenv()

# --- Env ---
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB = os.getenv("MONGO_DB", "")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# --- FastAPI app (note root_path for Vercel /api rewrite) ---
app = FastAPI(title="Telecom Hire Backend (FastAPI)", root_path="/api")

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- Mongo (lazy init for serverless) ---
_client: Optional[AsyncIOMotorClient] = None
_db = None
_col = None

async def get_collection():
    """ Lazily initialize and cache the Mongo collection. """
    global _client, _db, _col

    if _col is not None:
        return _col

    if not MONGO_URI or not MONGO_DB or not MONGO_COLLECTION:
        raise HTTPException(status_code=500, detail="Missing Mongo env vars")

    try:
        _client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _db = _client[MONGO_DB]
        _col = _db[MONGO_COLLECTION]
        # verify connectivity
        await _db.command("ping")
        # optional but recommended if you want unique primary email
        try:
            await _col.create_index("email_primary", unique=True)
        except Exception:
            # index might already exist; ignore
            pass
        return _col
    except Exception as e:
        # reset so we can retry next request
        _client = None
        _db = None
        _col = None
        raise HTTPException(status_code=500, detail=f"Mongo init failed: {e}")

# --- Models ---
class Submission(BaseModel):
    email_primary: EmailStr
    circle: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    district: str = Field(..., min_length=1)
    name: str = Field(..., min_length=2)
    contact_number: str = Field(..., min_length=7, max_length=20)
    pin_code: str = Field(..., min_length=3, max_length=12)
    designation: str
    activity: str
    work_at_height_certificate: str
    ppes: str
    submitted_at: Optional[datetime] = None

# --- Routes ---
@app.get("/health")
async def health():
    """Basic health check + Mongo connectivity status."""
    if not MONGO_URI or not MONGO_DB:
        return {"ok": True, "mongo": "not-configured"}
    try:
        # ping with a fresh lightweight client so this works even before lazy init
        c = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        await c.admin.command("ping")
        return {"ok": True, "mongo": "ok"}
    except Exception as e:
        return {"ok": False, "mongo": f"error: {e.__class__.__name__}"}

@app.get("/debug")
async def debug(col=Depends(get_collection)):
    """Return up to 10 docs (no _id) for quick inspection."""
    docs = []
    async for d in col.find({}, {"_id": False}).limit(10):
        docs.append(d)
    return {"count": len(docs), "docs": docs}

@app.post("/submit")
async def submit(data: Submission, col=Depends(get_collection)):
    doc = data.model_dump()
    doc["email_primary"] = doc["email_primary"].lower()
    doc["submitted_at"] = datetime.utcnow()

    try:
        res = await col.insert_one(doc)
        return {"ok": True, "id": str(res.inserted_id)}
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="email_primary already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
