# CrisisNet Monorepo Skeleton

This repository is scaffolded for rapid MVP development with:

- `frontend`: TypeScript React Native app (Expo) + Tailwind (`nativewind`)
- `backend`: FastAPI service with versioned API routing

## Repository Structure

```text
.
|-- frontend/
|   |-- App.tsx
|   |-- package.json
|   |-- tsconfig.json
|   |-- babel.config.js
|   |-- tailwind.config.js
|   |-- metro.config.js
|   |-- app.json
|   |-- src/
|   |   |-- components/
|   |   |   `-- StatusCard.tsx
|   |   |-- screens/
|   |   |   `-- HomeScreen.tsx
|   |   `-- types/
|   |       `-- domain.ts
|   `-- .gitignore
|-- backend/
|   |-- app/
|   |   |-- main.py
|   |   |-- core/
|   |   |   `-- config.py
|   |   `-- api/
|   |       `-- v1/
|   |           |-- api.py
|   |           `-- endpoints/
|   |               |-- alerts.py
|   |               |-- events.py
|   |               |-- health.py
|   |               `-- routes.py
|   |-- requirements.txt
|   |-- .env.example
|   |-- .gitignore
|   `-- tests/
|       `-- test_health.py
`-- .gitignore
```

## Quick Start

### 1) Frontend

```bash
cd frontend
npm install
npm run web
```

Then open browser devtools and use a mobile viewport preset for rapid UI testing.

### 2) Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open API docs at `http://127.0.0.1:8000/docs`.

## Notes on Web-First React Native Development

Building with Expo Web and testing in a mobile viewport is a good way to move fast on UI, navigation, and core state logic.

It is not exactly the same as native iOS/Android behavior. Differences show up in:

- Native permissions flow (microphone, GPS background behavior)
- Native-only modules and APIs
- Performance characteristics and gestures
- OS-level notifications/background execution

Recommended workflow:

1. Build UI and non-native logic first with `npm run web`.
2. Validate frequently on real device/emulator with `npm run android` / `npm run ios` once native features start.
3. Gate native-only functionality behind adapters/interfaces so web mocks stay productive.
