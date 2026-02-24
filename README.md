# Norrøna Alert

Monitor the Norrøna Outlet and get notified when products matching your size and preferences become available.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL + Redis
- **Frontend**: Next.js 14 + Tailwind + shadcn/ui + Capacitor (iOS)
- **Notifications**: Email (Resend), Web Push (VAPID), iOS Push (APNs)

## Setup

```bash
cp .env.example .env
docker-compose up -d
cd backend && pip install -e ".[dev]"
cd frontend && npm install
```

## Development

```bash
# Backend
cd backend && uvicorn src.main:app --reload

# Frontend
cd frontend && npm run dev
```
