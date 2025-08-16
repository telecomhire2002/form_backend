import os
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB = os.getenv("MONGO_DB", "")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()] or ["*"]
ALLOWED_ORIGINS = ["*"]

app = FastAPI(title="Telecom Hire Backend (FastAPI)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client: Optional[AsyncIOMotorClient] = None
collection = None

class Submission(BaseModel):
    email_primary: EmailStr
    email_alt: Optional[str] = ""
    circle: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    district: str = Field(..., min_length=1)
    name: str = Field(..., min_length=2)
    contact_number: str = Field(..., min_length=7)  # frontend enforces detailed pattern
    pin_code: str = Field(..., pattern=r"^\d{6}$")
    designation: str = Field(..., min_length=1)
    activity: str = Field(..., min_length=1)
    work_at_height_certificate: str = Field(..., pattern=r"^(YES|NO)$")
    ppes: str = Field(..., pattern=r"^(YES|NO)$")
    farm_tocli_number: Optional[str] = ""
    jbth_certificate_number: Optional[str] = ""

@app.on_event("startup")
async def on_startup():
    global client, collection
    if not MONGO_URI or not MONGO_DB or not MONGO_COLLECTION:
        return
    client = AsyncIOMotorClient(MONGO_URI, maxPoolSize=5)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]

    # Ensure ONLY primary email is unique
    await collection.create_index(
        "email_primary_lower",
        unique=True,
        sparse=True,
        name="uniq_email_primary_lower",
    )

    # Make alt email NON-unique (optional)
    try:
        await collection.drop_index("uniq_email_alt_lower")
    except Exception:
        pass
    await collection.create_index(
        "email_alt_lower",
        unique=False,
        sparse=True,
        name="idx_email_alt_lower",
    )

    # Add a regular index on pin_code for faster lookups
    await collection.create_index(
        "pin_code",
        unique=False,
        sparse=True,  # skips indexing if field is missing
        name="idx_pin_code",
    )


@app.get("/health")
async def health():
    if not MONGO_URI or not MONGO_DB:
        return {"status": "ok", "mongo": "not-configured"}
    try:
        c = AsyncIOMotorClient(MONGO_URI)
        await c.admin.command("ping")
        c.close()
        return {"status": "ok", "mongo": "connected"}
    except Exception as e:
        return {"status": "error", "mongo": str(e)}

@app.get("/debug")
async def debug():
    if collection is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    docs_cursor = collection.find(
        {}, projection={"_id": False, "email_primary": True, "submittedAt": True}
    ).sort("submittedAt", -1).limit(5)
    recent = [d async for d in docs_cursor]
    total = await collection.count_documents({})
    return {"count": total, "recent": recent}

@app.post("/submit")
async def submit(data: Submission):
    if collection is None:
        raise HTTPException(status_code=500, detail="MongoDB connection is not fully configured.")
    e1 = data.email_primary.lower()
    e2 = data.email_alt.lower() if data.email_alt else None

    # Friendly 409 if duplicate
    or_clauses = [{"email_primary_lower": e1}, {"email_alt_lower": e1}]
    if e2:
        or_clauses += [{"email_primary_lower": e2}, {"email_alt_lower": e2}]
    existing = await collection.find_one({"$or": or_clauses})
    if existing:
        raise HTTPException(status_code=409, detail="Duplicate submission detected for this email.")

    doc = data.model_dump()
    doc["email_primary_lower"] = e1
    doc["email_alt_lower"] = e2
    doc["submittedAt"] = datetime.utcnow().isoformat()

    try:
        result = await collection.insert_one(doc)
        return {"ok": True, "id": str(result.inserted_id)}
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Duplicate submission detected for this email.")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error: " + str(e))
