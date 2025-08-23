import os
from datetime import datetime
from typing import Optional, AsyncGenerator

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

# --- FastAPI app (routes mounted under /api/* via vercel.json) ---
app = FastAPI(title="Telecom Hire Backend (FastAPI)", root_path="/api")

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- Request-scoped Mongo dependency (yield) ---
async def get_collection() -> AsyncGenerator:
    if not MONGO_URI or not MONGO_DB or not MONGO_COLLECTION:
        raise HTTPException(status_code=500, detail="Missing Mongo env vars")

    client = AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=20000,
        connectTimeoutMS=20000,
        socketTimeoutMS=20000,
        tls=True,
        tlsAllowInvalidCertificates=False,
    )
    try:
        db = client[MONGO_DB]
        col = db[MONGO_COLLECTION]
        # Verify connectivity; fail fast if blocked
        await db.command("ping")
        # Optional unique index on primary email
        try:
            await col.create_index("email_primary", unique=True)
        except Exception:
            pass
        yield col
    finally:
        client.close()

# --- Models ---
class Submission(BaseModel):
    email_primary: EmailStr
    email_alt: Optional[str] = None   # new
    circle: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    district: str = Field(..., min_length=1)
    education_qualification: Optional[str] = None  # new
    name: str = Field(..., min_length=2)
    contact_number: str = Field(..., min_length=7, max_length=20)
    pin_code: str = Field(..., min_length=3, max_length=12)
    designation: str
    activity: str
    work_at_height_certificate: str
    jbth_certificate_number: Optional[str] = None  # new
    farm_tocli_number: Optional[str] = None        # new
    ppes: str
    submitted_at: Optional[datetime] = None

# --- Routes ---
@app.get("/health")
async def health():
    if not MONGO_URI or not MONGO_DB:
        return {"ok": True, "mongo": "not-configured"}
    client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000, tls=True)
    try:
        await client.admin.command("ping")
        return {"ok": True, "mongo": "ok"}
    except Exception as e:
        return {"ok": False, "mongo": f"error: {e.__class__.__name__}"}
    finally:
        client.close()

@app.get("/debug")
async def debug(col=Depends(get_collection)):
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
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}" )
