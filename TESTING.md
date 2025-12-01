# Testing Guide - Frontend-Backend Connection

## Prerequisites

1. **Backend running:**
   ```bash
   cd backend
   source venv/bin/activate  # or activate your virtual environment
   uvicorn app.main:app --reload
   ```
   Backend should be running at `http://localhost:8000`

2. **Frontend running:**
   ```bash
   cd frontend
   npm install  # First time only
   npm run dev
   ```
   Frontend should be running at `http://localhost:3000`

3. **Database setup:**
   - Make sure PostgreSQL is running
   - Run migrations: `cd backend && alembic upgrade head`
   - Or create database manually if needed

4. **Environment variables:**
   - Backend: `.env` file with `DATABASE_URL`, `JWT_SECRET_KEY`, `OPENAI_API_KEY`
   - Frontend: `.env.local` file with `NEXT_PUBLIC_API_URL=http://localhost:8000`

## Testing Flow

### 1. Test Registration
- Go to `http://localhost:3000/register`
- Fill in email, username, password
- Submit form
- **Expected:** Redirects to `/onboarding`

### 2. Test Onboarding
- Medical History form should appear
- Fill in medical information (optional)
- Click "Continue"
- Fill in preferences (optional)
- Click "Complete Setup"
- **Expected:** Redirects to `/dashboard`

### 3. Test Dashboard & Agent Chat
- Dashboard should load with welcome message
- Type a message like "I want to start working out"
- Click Send
- **Expected:** Agent responds with workout recommendations

### 4. Test Medical Conflict Detection
- If you entered medical conditions in onboarding, try asking for exercises that conflict
- Example: If you have "knee injury", ask "Can I do squats?"
- **Expected:** Agent warns about conflicts and suggests alternatives

### 5. Test Login Flow
- Logout from dashboard
- Go to `/login`
- Login with registered credentials
- **Expected:** Redirects to `/dashboard`

## API Endpoints to Verify

You can also test directly via Swagger UI:
- Go to `http://localhost:8000/docs`
- Test endpoints manually:
  - `POST /auth/register`
  - `POST /auth/login`
  - `POST /medical/history`
  - `POST /agents/physical-fitness/chat`

## Common Issues

1. **CORS errors:** Make sure backend CORS allows `http://localhost:3000`
2. **401 Unauthorized:** Check token is being stored and sent in headers
3. **Connection refused:** Verify both servers are running
4. **Agent not responding:** Check OpenAI API key is set correctly

## Quick Test Commands

```bash
# Test backend health
curl http://localhost:8000/health

# Test registration (from project root)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","username":"testuser","password":"test123"}'

# Test login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}'
```

