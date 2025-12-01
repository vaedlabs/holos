# Holos Backend

FastAPI backend for the Holos AI Fitness Application.

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- OpenAI API key

### Installation

1. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your actual values
```

4. Set up the database:
```bash
# Create PostgreSQL database
createdb holos_db

# Option 1: Use setup script (recommended for MVP)
python setup_database.py

# Option 2: Use Alembic migrations
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

5. Run the development server:
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure

```
backend/
├── app/
│   ├── agents/          # LangChain agents
│   ├── models/          # SQLAlchemy database models
│   │   ├── user.py      # User model
│   │   ├── medical_history.py  # Medical history model
│   │   ├── user_preferences.py # User preferences model
│   │   ├── workout_log.py      # Workout log model
│   │   └── conversation_message.py  # Conversation history model
│   ├── routers/         # FastAPI route handlers
│   ├── services/        # Business logic
│   ├── schemas/         # Pydantic schemas
│   ├── database.py      # Database configuration
│   ├── dependencies.py  # FastAPI dependencies
│   └── main.py          # FastAPI application
├── alembic/             # Database migrations
│   ├── versions/        # Migration files
│   └── env.py           # Alembic environment
├── alembic.ini          # Alembic configuration
├── requirements.txt     # Python dependencies
└── .env.example         # Environment variables template
```

## Database Models

- **User**: Authentication (email, username, password_hash, timestamps)
- **MedicalHistory**: Medical conditions, limitations, medications, notes
- **UserPreferences**: Fitness goals, dietary restrictions, location, exercise types, activity level
- **WorkoutLog**: Workout entries with date, exercise type, exercises, duration, notes
- **ConversationMessage**: Chat history with role (user/assistant), content, warnings, timestamps

## API Endpoints

### Authentication
- `POST /auth/register` - Register new user (email, username, password)
- `POST /auth/login` - Login user (email, password) → returns JWT token

### Medical History
- `GET /medical/history` - Get current user's medical history (requires auth)
- `POST /medical/history` - Create or update medical history (requires auth)

### User Preferences
- `GET /preferences` - Get current user's preferences (requires auth)
- `POST /preferences` - Create or update preferences (requires auth)

### Physical Fitness Agent
- `POST /agents/physical-fitness/chat` - Send message to agent (requires auth)
  - Request: `{ "message": "user message" }`
  - Response: `{ "response": "agent response", "warnings": [...] }`

### Conversation History
- `POST /messages` - Save a conversation message (requires auth)
- `GET /messages` - Get conversation history (requires auth)
- `DELETE /messages` - Clear conversation history (requires auth)

### Workout Logs
- `GET /logs/workouts` - Get user's workout logs (requires auth)
  - Query params: `page` (default: 1), `limit` (default: 10), `order` (asc/desc)

**Full interactive documentation**: Visit `http://localhost:8000/docs` when server is running

## Environment Variables

See `.env.example` for required environment variables. Create a `.env` file with:

- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql://user:password@localhost:5432/holos_db`)
- `JWT_SECRET_KEY`: Secret key for JWT tokens (minimum 32 characters, use `openssl rand -hex 32`)
- `JWT_ALGORITHM`: JWT algorithm (default: `HS256`)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: Token expiration in minutes (default: `1440` = 24 hours)
- `OPENAI_API_KEY`: OpenAI API key for Physical Fitness Agent (format: `sk-...`)
- `ENVIRONMENT`: Environment name (default: `development`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

**Important**: Never commit `.env` to version control. Always use `.env.example` as a template.

## Testing

### Test Setup

Run the setup test to verify everything is configured correctly:

```bash
python test_setup.py
```

This will test:
- All imports work correctly
- Environment variables are set
- Models are properly defined
- Auth functions work
- Medical service conflict detection
- Database connection

### Test API Endpoints

After starting the server, test the API endpoints:

```bash
# In a separate terminal, start the server first:
uvicorn app.main:app --reload

# Then run API tests:
python test_api.py
```

### Test Agent Endpoints

Test the Physical Fitness Agent and related functionality:

```bash
# Make sure server is running first:
uvicorn app.main:app --reload

# Then run agent tests:
python test_agent.py
```

This will test:
- Agent chat endpoint
- Medical conflict detection
- Workout log creation through agent

Or test manually using the Swagger UI at `http://localhost:8000/docs`

