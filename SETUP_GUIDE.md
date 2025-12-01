# Holos MVP - Complete Setup Guide

This guide will walk you through setting up the Holos AI Fitness Application MVP from scratch.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **Node.js 18+** - [Download](https://nodejs.org/)
- **PostgreSQL 14+** - [Download](https://www.postgresql.org/download/)
- **OpenAI API Key** - [Get one here](https://platform.openai.com/api-keys)

## Step 1: Clone and Navigate to Project

```bash
# If you haven't already, navigate to the project directory
cd holos
```

## Step 2: Backend Setup

### 2.1 Create Virtual Environment

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2.2 Install Dependencies

```bash
pip install -r requirements.txt
```

### 2.3 Configure Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
cp .env.example .env
# Or create .env manually
```

Edit `.env` with your actual values:

```env
# Database
DATABASE_URL=postgresql://username:password@localhost:5432/holos_db

# JWT Authentication
JWT_SECRET_KEY=your-secret-key-here-minimum-32-characters-long
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# OpenAI API
OPENAI_API_KEY=sk-your-openai-api-key-here

# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO
```

**Important Notes:**
- Replace `username` and `password` with your PostgreSQL credentials
- Generate a secure `JWT_SECRET_KEY` (you can use: `openssl rand -hex 32`)
- Get your OpenAI API key from [platform.openai.com](https://platform.openai.com/api-keys)

### 2.4 Set Up Database

**Option A: Using Setup Script (Recommended for MVP)**

```bash
# Make sure PostgreSQL is running and create the database first
createdb holos_db

# Run the setup script
python setup_database.py
```

**Option B: Using Alembic Migrations**

```bash
# Create the database
createdb holos_db

# Generate initial migration
alembic revision --autogenerate -m "Initial migration"

# Apply migrations
alembic upgrade head
```

### 2.5 Verify Backend Setup

Test that everything is configured correctly:

```bash
python test_setup.py
```

This will verify:
- All imports work
- Environment variables are set
- Models are properly defined
- Auth functions work
- Database connection

### 2.6 Start Backend Server

```bash
uvicorn app.main:app --reload
```

The backend API will be available at:
- **API**: `http://localhost:8000`
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Step 3: Frontend Setup

### 3.1 Install Dependencies

Open a new terminal window:

```bash
cd frontend
npm install
```

### 3.2 Configure Environment Variables

Create a `.env.local` file in the `frontend/` directory:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3.3 Start Frontend Server

```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`

## Step 4: Verify Installation

### 4.1 Test Backend Health

```bash
curl http://localhost:8000/health
```

Expected response: `{"status": "healthy"}`

### 4.2 Test Frontend Connection

1. Open `http://localhost:3000` in your browser
2. You should see the Holos home page
3. Click "Register" to create an account

### 4.3 Complete User Flow

1. **Register**: Create a new account at `/register`
2. **Onboarding**: Complete medical history and preferences at `/onboarding`
3. **Dashboard**: Chat with the Physical Fitness Agent at `/dashboard`
4. **Test Agent**: Ask questions like:
   - "I want to start working out"
   - "Create a workout plan for me"
   - "What exercises should I avoid with my condition?"

## Step 5: Troubleshooting

### Backend Issues

**Database Connection Error**
```
Error: could not connect to server
```
**Solution**: 
- Verify PostgreSQL is running: `pg_isready`
- Check `DATABASE_URL` in `.env` matches your PostgreSQL setup
- Ensure database exists: `createdb holos_db`

**Module Not Found Error**
```
ModuleNotFoundError: No module named 'app'
```
**Solution**: 
- Make sure you're in the `backend/` directory when running commands
- Activate virtual environment: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

**JWT Token Error**
```
JWTError: Invalid token
```
**Solution**:
- Check `JWT_SECRET_KEY` is set in `.env`
- Ensure token is being sent in Authorization header
- Verify token hasn't expired (default: 24 hours)

**OpenAI API Error**
```
Error: Missing bearer or basic authentication in header
```
**Solution**:
- Verify `OPENAI_API_KEY` is set correctly in `.env`
- Check API key is valid at [platform.openai.com](https://platform.openai.com/api-keys)
- Ensure you have billing set up if using paid models

### Frontend Issues

**Cannot Connect to Backend**
```
Failed to fetch
```
**Solution**:
- Verify backend is running at `http://localhost:8000`
- Check `NEXT_PUBLIC_API_URL` in `.env.local`
- Ensure CORS is configured in backend (should be set to allow `http://localhost:3000`)

**401 Unauthorized Error**
```
401 Unauthorized
```
**Solution**:
- Clear browser localStorage: `localStorage.clear()`
- Log in again to get a fresh token
- Check token is being stored: Open DevTools → Application → Local Storage

**Build Errors**
```
Build Error: × Expected '</', got 'jsx text'
```
**Solution**:
- Check for unclosed JSX tags
- Verify all components have proper closing tags
- Run `npm run build` to see detailed error messages

### Database Issues

**Tables Don't Exist**
```
relation "users" does not exist
```
**Solution**:
- Run database setup: `python backend/setup_database.py`
- Or run migrations: `cd backend && alembic upgrade head`

**Migration Errors**
```
alembic: command not found
```
**Solution**:
- Install Alembic: `pip install alembic`
- Or use the setup script instead: `python setup_database.py`

## Quick Reference

### Backend Commands

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Start server
uvicorn app.main:app --reload

# Run tests
python test_setup.py
python test_api.py

# Database setup
python setup_database.py
# OR
alembic upgrade head
```

### Frontend Commands

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

### Environment Variables Summary

**Backend (`.env`):**
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET_KEY` - Secret for JWT tokens
- `JWT_ALGORITHM` - JWT algorithm (default: HS256)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiration (default: 1440)
- `OPENAI_API_KEY` - OpenAI API key
- `ENVIRONMENT` - Environment name (development/production)
- `LOG_LEVEL` - Logging level (INFO/DEBUG)

**Frontend (`.env.local`):**
- `NEXT_PUBLIC_API_URL` - Backend API URL (default: http://localhost:8000)

## Next Steps

Once setup is complete:

1. **Explore the API**: Visit `http://localhost:8000/docs` to see all available endpoints
2. **Test the Agent**: Try different queries in the dashboard chat
3. **Check Medical Warnings**: Enter medical conditions and see conflict detection in action
4. **View Workout Logs**: Ask the agent to log workouts and view them in the dashboard

## Support

For issues or questions:
- Check the [TASKS.md](./TASKS.md) for feature documentation
- Review [TESTING.md](./TESTING.md) for testing procedures
- Check backend logs for detailed error messages
- Review frontend console (F12) for client-side errors

