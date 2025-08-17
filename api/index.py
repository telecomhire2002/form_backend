# Expose your FastAPI ASGI app to Vercel
# Vercel's Python runtime will look for a module-level variable named `app`.
# We import your FastAPI `app` from main.py and re-export it here.
from main import app  # noqa: F401
