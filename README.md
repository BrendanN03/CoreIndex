# CoreIndex — Run Instructions

## Backend (FastAPI)

From the repo root:

```bash
cd "apps/api/app"

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

