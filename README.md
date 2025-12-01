# Holos - AI Fitness Application

AI-powered fitness application with specialized agents for physical fitness, nutrition, and mental wellness.

## Features

- **4 Specialized AI Agents**:
  - 💪 Physical Fitness Agent (OpenAI) - Workout planning, exercise recommendations
  - 🥗 Nutrition Agent (Gemini) - Meal planning with geographic awareness
  - 🧘 Mental Fitness Agent (OpenAI) - Mindfulness and stress management
  - 🎯 Coordinator Agent (OpenAI) - Holistic cross-domain recommendations

- **Medical Safety**: Exercise conflict detection based on medical history
- **Geographic Nutrition**: Location-aware food recommendations
- **Multiple Exercise Types**: Calisthenics, weight lifting, powerlifting, pilates, yoga, cardio, HIIT, and more
- **Persuasive Recommendations**: Agents provide adamant, evidence-based guidance
- **Real-time Streaming**: WebSocket support for live agent responses

## Quick Start

See [SETUP_GUIDE.md](./SETUP_GUIDE.md) for complete step-by-step instructions.

### Quick Commands

**Backend:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Configure .env file
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
# Configure .env.local
npm run dev
```

## Project Structure

```
holos/
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── agents/   # LangChain agents
│   │   ├── models/   # Database models
│   │   ├── routers/  # API routes
│   │   └── services/ # Business logic
│   └── alembic/      # Database migrations
├── frontend/         # Next.js frontend
│   ├── app/          # Pages
│   └── components/   # React components
└── SETUP_GUIDE.md    # Complete setup instructions
```

## Requirements

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- API Keys: OpenAI, Google Gemini, Tavily (for web search)

## Documentation

- [Complete Setup Guide](./SETUP_GUIDE.md) - Step-by-step installation instructions
- [Backend README](./backend/README.md) - Backend setup and API documentation
- [Frontend README](./frontend/README.md) - Frontend setup instructions
- [Testing Guide](./TESTING.md) - Testing procedures and common issues
- [Task Breakdown](./TASKS.md) - Detailed MVP sprint plan

## API Endpoints

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/login` - Login user

### Medical History
- `GET /medical/history` - Get user's medical history
- `POST /medical/history` - Create/update medical history

### User Preferences
- `GET /preferences` - Get user preferences
- `POST /preferences` - Create/update preferences

### Physical Fitness Agent
- `POST /agents/physical-fitness/chat` - Chat with Physical Fitness Agent

### Conversation
- `POST /messages` - Save conversation message
- `GET /messages` - Get conversation history
- `DELETE /messages` - Clear conversation history

### Workout Logs
- `GET /logs/workouts` - Get user's workout logs (with pagination)

**Full API Documentation**: Visit `http://localhost:8000/docs` when backend is running

## License

MIT
