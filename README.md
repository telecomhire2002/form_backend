# FastAPI + Vercel + MongoDB (Motor)

This repo deploys a FastAPI backend to **Vercel** and connects to **MongoDB Atlas**.

## Endpoints
- `GET /api/health` — basic health check
- `GET /api/debug` — returns up to 10 docs (sanitized)
- `POST /api/submit` — inserts a submission

## Environment Variables
- `MONGO_URI`, `MONGO_DB`, `MONGO_COLLECTION`
- `ALLOWED_ORIGINS` — comma-separated origins for CORS (optional)

## Local Dev
```bash
pip install -r requirements.txt
export MONGO_URI="..."
export MONGO_DB="..."
export MONGO_COLLECTION="..."
export ALLOWED_ORIGINS="http://localhost:5173,http://localhost:3000"
uvicorn main:app --reload
```

## Deploy to Vercel
- Install CLI: `npm i -g vercel`
- Run `vercel` then `vercel --prod`
- Calls are made to `/api/*` paths.
