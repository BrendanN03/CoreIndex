# CoreIndex — Run Instructions

## One command (API + web + optional local factoring stub)

From the repo root, after `npm install` in `apps/web` and a Python venv in `apps/api` with `pip install -r apps/api/requirements.txt`:

```bash
npm run dev
```

- Web: http://127.0.0.1:5173  
- API: http://127.0.0.1:8010  

In **development**, the React app calls the API at **`http://127.0.0.1:8010` by default** (see `apps/web/src/lib/api.ts`) so the browser does not depend on the Vite `/coreindex-api` proxy (which can appear to hang). Override with `VITE_API_BASE_URL` if needed. API liveness: `http://127.0.0.1:8010/health` (or `/`).

If the **Physical Delivery** demo fails on “connection refused” to `FACTORING_REMOTE_HTTP_URL` (default `http://127.0.0.1:8000`), either:

1. **Local dev stub** (trial division, no GPU):  
   `COREINDEX_DEV_FACTOR_STUB=1 npm run dev`  
   (starts `dev_remote_factor_server` on port 8000 alongside the API), **or**

2. **Manual stub** in a second terminal:  
   `cd apps/api && .venv/bin/python -m uvicorn dev_remote_factor_server:app --host 127.0.0.1 --port 8000`  
   with `FACTORING_REMOTE_HTTP_URL=http://127.0.0.1:8000` in `apps/api/.env`.

Ensure `requests` is installed in the API venv (`pip install -r apps/api/requirements.txt`).

## Backend (FastAPI)

From the repo root:

```bash
cd "apps/api"

# Create a virtual environment (if you don’t already have one)
python -m venv ../venv

# Activate it
source ../venv/bin/activate

# Install dependencies
pip install -r ../requirements.txt

# Run the API (note the PYTHONPATH)
PYTHONPATH=../.. python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Useful URLs:
- `http://localhost:8000/` (health)
- `http://localhost:8000/docs` (Swagger UI)

## Frontend (Vite + React)

In a second terminal, from the repo root:

```bash
cd "apps/web"
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`).

