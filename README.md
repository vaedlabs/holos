# Holos - AI Fitness Application

AI-powered fitness application with specialized agents for physical fitness, nutrition, and mental wellness.

## Features

- **4 Specialized AI Agents**:
  - 💪 Physical Fitness Agent (OpenAI) - Workout planning, exercise recommendations
  - 🥗 Nutrition Agent (Gemini) - Meal planning with geographic awareness and **image-based calorie tracking**
  - 🧘 Mental Fitness Agent (OpenAI) - Mindfulness and stress management
  - 🎯 Coordinator Agent (OpenAI) - Intelligent routing and holistic cross-domain planning

- **Medical Safety**: Exercise conflict detection based on medical history
- **Image-Based Calorie Tracking**: Upload food images for automatic calorie and macro analysis using Gemini Vision
- **Geographic Nutrition**: Location-aware food recommendations
- **Multiple Exercise Types**: Calisthenics, weight lifting, powerlifting, pilates, yoga, cardio, HIIT, and more
- **Holistic Planning**: Coordinator Agent creates comprehensive wellness plans combining all three domains
- **Conversation Persistence**: Chat history and images are saved and persist across sessions

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

### AI Agents
- `POST /agents/physical-fitness/chat` - Chat with Physical Fitness Agent
- `POST /agents/nutrition/chat` - Chat with Nutrition Agent (supports image uploads for food analysis)
- `POST /agents/mental-fitness/chat` - Chat with Mental Fitness Agent
- `POST /agents/coordinator/chat` - Chat with Coordinator Agent (routes queries or creates holistic plans)

### Conversation
- `POST /conversation/messages` - Save conversation message (supports image storage)
- `GET /conversation/messages` - Get conversation history (includes image references)
- `DELETE /conversation/messages` - Clear conversation history
- `POST /conversation/upload-image` - Upload and store image for conversation messages
- `GET /uploads/images/{filename}` - Retrieve stored conversation images

### Logs
- `GET /logs/workouts` - Get user's workout logs (with pagination)
- `GET /logs/nutrition` - Get user's nutrition logs (with pagination)
- `GET /logs/mental-fitness` - Get user's mental fitness logs (with pagination)

**Full API Documentation**: Visit `http://localhost:8000/docs` when backend is running

## License

MIT
