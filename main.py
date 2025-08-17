import os
from typing import Optional, Annotated, List
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB = os.getenv("MONGO_DB", "")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

client: Optional[AsyncIOMotorClient] = None
collection = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, collection
    if not MONGO_URI or not MONGO_DB or not MONGO_COLLECTION:
        raise RuntimeError("Missing MONGO_URI/MONGO_DB/MONGO_COLLECTION env vars")
    client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]
    # Optional: ping once to fail fast if network blocked
    await db.command("ping")
    # Optional: ensure index if you want uniqueness on primary email
    await collection.create_index("email_primary", unique=True)
    yield
    # Do not close client to allow instance reuse on Vercel

app = FastAPI(title="Telecom Hire Backend (FastAPI)", root_path="/api", lifespan=lifespan)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

class Submission(BaseModel):
    email_primary: EmailStr
    email_alt: Optional[EmailStr] = None
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

async def get_collection():
    if collection is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    return collection

@app.get("/health")
async def health():
    try:
        if not MONGO_URI:
            return {"ok": True, "mongo": "not-configured"}
        c = AsyncIOMotorClient(MONGO_URI)
        await c.admin.command("ping")
        return {"ok": True, "mongo": "ok"}
    except Exception as e:
        return {"ok": False, "mongo": f"error: {e.__class__.__name__}"}

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
    if doc.get("email_alt"):
        doc["email_alt"] = doc["email_alt"].lower()
    doc["submitted_at"] = datetime.utcnow()

    try:
        res = await col.insert_one(doc)
        return {"ok": True, "id": str(res.inserted_id)}
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="email_primary already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}") from e
