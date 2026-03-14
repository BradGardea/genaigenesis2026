# Backend (FastAPI)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

## Available Starter Endpoints

- `GET /api/v1/health`
- `GET /api/v1/alerts/signals`
- `GET /api/v1/events/active`
- `POST /api/v1/routes/plan`

Swagger docs:

- `http://127.0.0.1:8000/docs`

