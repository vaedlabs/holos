# Holos Backend

FastAPI backend for the Holos AI Fitness Application.

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- API Keys:
  - OpenAI API key (for Physical Fitness, Mental Fitness, and Coordinator agents)
  - Google Gemini API key (for Nutrition Agent with image analysis)
  - Tavily API key (for web search tool)

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
- **ConversationMessage**: Chat history with role (user/assistant), content, warnings, image_path, timestamps
- **NutritionLog**: Meal entries with date, meal_type, foods, calories, macros, notes
- **MentalFitnessLog**: Mental wellness activities with date, activity_type, duration, mood tracking, notes

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

### AI Agents
- `POST /agents/physical-fitness/chat` - Chat with Physical Fitness Agent (requires auth)
  - Request: `{ "message": "user message", "agent_type": "physical-fitness" }`
  - Response: `{ "response": "agent response", "warnings": [...] }`

- `POST /agents/nutrition/chat` - Chat with Nutrition Agent (requires auth)
  - Request: `{ "message": "user message", "agent_type": "nutrition", "image_base64": "optional base64 image" }`
  - Response: `{ "response": "agent response", "warnings": [...], "nutrition_analysis": {...} }`
  - **Image Analysis**: Upload food images (base64) for automatic calorie and macro analysis

- `POST /agents/mental-fitness/chat` - Chat with Mental Fitness Agent (requires auth)
  - Request: `{ "message": "user message", "agent_type": "mental-fitness" }`
  - Response: `{ "response": "agent response", "warnings": [...] }`

- `POST /agents/coordinator/chat` - Chat with Coordinator Agent (requires auth)
  - Request: `{ "message": "user message", "agent_type": "coordinator", "image_base64": "optional" }`
  - Response: `{ "response": "agent response", "warnings": [...], "nutrition_analysis": {...} }`
  - **Routing**: Automatically routes queries to appropriate agent or creates holistic plans

### Conversation History
- `POST /conversation/messages` - Save a conversation message (requires auth)
  - Request: `{ "role": "user|assistant", "content": "message text", "warnings": [...], "image_path": "optional" }`
- `GET /conversation/messages` - Get conversation history (requires auth)
  - Response: `{ "messages": [...] }` (includes image_path for messages with images)
- `DELETE /conversation/messages` - Clear conversation history (requires auth)
- `POST /conversation/upload-image` - Upload and store image for conversation (requires auth)
  - Request: `{ "image_base64": "base64 encoded image" }`
  - Response: `{ "image_path": "images/filename.jpg" }`
- `GET /uploads/images/{filename}` - Retrieve stored conversation images (public)

### Logs
- `GET /logs/workouts` - Get user's workout logs (requires auth)
  - Query params: `limit` (default: 50), `offset` (default: 0)
- `GET /logs/nutrition` - Get user's nutrition logs (requires auth)
  - Query params: `limit` (default: 50), `offset` (default: 0)
- `GET /logs/mental-fitness` - Get user's mental fitness logs (requires auth)
  - Query params: `limit` (default: 50), `offset` (default: 0)

**Full interactive documentation**: Visit `http://localhost:8000/docs` when server is running

## Environment Variables

See `.env.example` for required environment variables. Create a `.env` file with:

- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql://user:password@localhost:5432/holos_db`)
- `JWT_SECRET_KEY`: Secret key for JWT tokens (minimum 32 characters, use `openssl rand -hex 32`)
- `JWT_ALGORITHM`: JWT algorithm (default: `HS256`)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: Token expiration in minutes (default: `1440` = 24 hours)
- `OPENAI_API_KEY`: OpenAI API key for Physical Fitness Agent (format: `sk-...`)
- `GOOGLE_GEMINI_API_KEY`: Google Gemini API key for Nutrition Agent with vision capabilities (get from https://makersuite.google.com/app/apikey)
- `TAVILY_API_KEY`: Tavily API key for web search tool (get from https://tavily.com)
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
- Physical Fitness Agent chat endpoint
- Medical conflict detection
- Workout log creation through agent
- Nutrition Agent (text queries and image analysis)
- Mental Fitness Agent
- Coordinator Agent (routing and holistic planning)

Or test manually using the Swagger UI at `http://localhost:8000/docs`

## Image Upload API Usage

### Uploading Images for Conversation

Images can be uploaded and stored with conversation messages. This is particularly useful for the Nutrition Agent's image-based calorie tracking feature.

**Step 1: Upload Image**
```bash
POST /conversation/upload-image
Headers: Authorization: Bearer <token>
Body: {
  "image_base64": "base64_encoded_image_string"
}
Response: {
  "image_path": "images/user123_abc12345.jpg"
}
```

**Step 2: Save Message with Image Path**
```bash
POST /conversation/messages
Headers: Authorization: Bearer <token>
Body: {
  "role": "user",
  "content": "How many calories in this?",
  "image_path": "images/user123_abc12345.jpg"
}
```

**Step 3: Retrieve Image**
```bash
GET /uploads/images/user123_abc12345.jpg
# Returns the image file
```

### Using with Nutrition Agent

When sending a message to the Nutrition Agent with an image:

```bash
POST /agents/nutrition/chat
Headers: Authorization: Bearer <token>
Body: {
  "message": "How many calories in this food?",
  "agent_type": "nutrition",
  "image_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
}
Response: {
  "response": "Blueberry pie slice: ~380 calories...",
  "nutrition_analysis": {
    "calories": 380,
    "macros": {
      "protein": 4.5,
      "carbs": 52.0,
      "fats": 18.0
    },
    "foods": ["Blueberry pie", "Whipped cream"],
    "meal_type": "dessert"
  }
}
```

**Note**: The `image_base64` field should contain the base64-encoded image data. You can include the data URL prefix (`data:image/jpeg;base64,`) or just the base64 string - both formats are supported.

