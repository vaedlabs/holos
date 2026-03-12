# Holos MVP - Setup Guide

## Prerequisites

- Python 3.12+
- Node.js 20+ (developed on 24.11+)
- PostgreSQL 14+
- API keys for OpenAI and Google Gemini (Tavily is optional)

---

## 1. Backend

### Virtual environment

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Environment variables

```bash
cp .env.example .env
```

Fill in `.env`:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/holos_db
JWT_SECRET_KEY=your-secret-key-minimum-32-characters
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
OPENAI_API_KEY=sk-your-key
GOOGLE_GEMINI_API_KEY=your-gemini-key
TAVILY_API_KEY=your-tavily-key
ENVIRONMENT=development
LOG_LEVEL=INFO
```

Generate a JWT secret with `openssl rand -hex 32` if you don't have one.

**Where to get the keys:**
- OpenAI: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- Gemini: [makersuite.google.com/app/apikey](https://makersuite.google.com/app/apikey) — needed for the Nutrition Agent's image analysis
- Tavily: [tavily.com](https://tavily.com) — optional, enables web search in agents

### Database

```bash
createdb holos_db
python setup_database.py  # or: alembic upgrade head
```

### Start the server

```bash
uvicorn app.main:app --reload
```

API at `http://localhost:8000`. Swagger at `http://localhost:8000/docs`.

---

## 2. Frontend

Open a new terminal:

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Start it:

```bash
npm run dev
```

App at `http://localhost:3000`.

---

## 3. Verify It's Working

```bash
curl http://localhost:8000/health
# {"status": "healthy"}
```

Then open `http://localhost:3000`, register an account, go through onboarding, and try the dashboard. Ask the Physical Fitness Agent something — if it responds, everything's wired up correctly.

---

## 4. Troubleshooting

**Database connection error**
- Check PostgreSQL is running: `pg_isready`
- Make sure `holos_db` exists: `createdb holos_db`
- Verify `DATABASE_URL` matches your setup

**ModuleNotFoundError**
- You're probably not in `backend/` or the venv isn't active
- `source venv/bin/activate`, then try again

**401 errors**
- Clear localStorage and log in again
- Check `JWT_SECRET_KEY` is set in `.env`

**Frontend can't reach backend**
- Both servers need to be running
- Check `NEXT_PUBLIC_API_URL` in `.env.local`
- Make sure CORS allows `http://localhost:3000`

**Tables don't exist**
- `python setup_database.py` or `alembic upgrade head` from `backend/`

**Agent not responding**
- Check the relevant API key in `.env`
- Look at backend logs for the actual error

---

## 5. Quick Reference

```bash
# Backend
source venv/bin/activate
uvicorn app.main:app --reload
python setup_database.py

# Frontend
npm run dev
npm run build
```

---

## Next Steps

- Swagger at `http://localhost:8000/docs` has every endpoint
- Try the Nutrition Agent with a food image — upload a photo and ask for the calorie count
- Add a medical condition in onboarding and see the conflict detection kick in when asking for workout recommendations
- Check **TESTING.md** for a full end-to-end test flow