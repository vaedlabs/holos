# Post-MVP Agent Expansion Plan

## Overview

Expand Holos from a single Physical Fitness Agent to a multi-agent system with Nutrition Agent (Gemini), Mental Fitness Agent (OpenAI), and a Coordinator Agent that routes queries and creates holistic plans. Add web search capabilities and nutrition/mental fitness logging.

## Phase 1: Database Models & Logging Infrastructure

### 1.1 Create Nutrition Log Model

- **File**: `backend/app/models/nutrition_log.py`
- **Structure**: Similar to `WorkoutLog` with fields:
- `meal_date`, `meal_type` (breakfast/lunch/dinner/snack), `foods` (JSON), `calories`, `macros` (JSON), `notes`
- **Relationship**: Add to `User` model in `backend/app/models/user.py`
- **Migration**: Create Alembic migration for `nutrition_logs` table

### 1.2 Create Mental Fitness Log Model

- **File**: `backend/app/models/mental_fitness_log.py`
- **Structure**: Similar to `WorkoutLog` with fields:
- `activity_date`, `activity_type` (meditation/mindfulness/journaling/etc.), `duration_minutes`, `mood_before`, `mood_after`, `notes`
- **Relationship**: Add to `User` model
- **Migration**: Create Alembic migration for `mental_fitness_logs` table

### 1.3 Update Models Export

- **File**: `backend/app/models/__init__.py`
- Add `NutritionLog` and `MentalFitnessLog` to exports

## Phase 2: Web Search Tool

### 2.1 Add Web Search Tool to Base Agent

- **File**: `backend/app/agents/base_agent.py`
- **Dependencies**: Add `tavily-python` to `backend/requirements.txt`
- **Tool**: Create `WebSearchTool` class extending `BaseTool`
- Use Tavily API for web search
- Input: search query string
- Output: formatted search results
- **Integration**: Add tool to `BaseAgent.__init__` tools list
- **Environment**: Add `TAVILY_API_KEY` to `.env.example`

## Phase 3: Nutrition Agent (Gemini)

### 3.1 Install Gemini Dependencies

- **File**: `backend/requirements.txt`
- Add `google-generativeai` package

### 3.2 Create Gemini Base Agent Support

- **File**: `backend/app/agents/gemini_base_agent.py` (optional, or extend BaseAgent)
- **Alternative**: Modify `BaseAgent` to support both OpenAI and Gemini
- **Implementation**: Create Gemini-compatible agent base class or add model selection to `BaseAgent`

### 3.3 Create Nutrition Agent

- **File**: `backend/app/agents/nutrition_agent.py`
- **Extends**: Base agent (or Gemini-specific base)
- **Model**: Use Gemini Vision-capable model (via `ChatGoogleGenerativeAI` from LangChain with vision support)
- **System Prompt**: Specialized for nutrition, meal planning, dietary advice, and **image-based food analysis**
- **Tools**: 
- Inherit base tools (medical history, preferences)
- Add `CreateNutritionLogTool` (similar to `CreateWorkoutLogTool`)
- Add web search tool for food/nutrition info
- **Location Awareness**: Use `UserPreferences.location` for geographic food recommendations
- **KEY FEATURE - Image Analysis**:
- Accept base64-encoded food images in chat requests
- Use Gemini Vision API to analyze food photos
- Extract: food items, portion sizes, estimated calories, macros (protein/carbs/fats)
- Identify meal type (breakfast/lunch/dinner/snack) from context
- Return structured nutrition data that can auto-populate nutrition log
- Handle multiple foods in single image
- Provide confidence estimates for calorie/macro calculations

### 3.4 Create Nutrition Log Tool

- **File**: `backend/app/agents/base_agent.py` (or separate tools file)
- **Tool**: `CreateNutritionLogTool` extending `BaseTool`
- **Fields**: meal_date, meal_type, foods, calories, macros, notes
- **Model**: Use `NutritionLog` model

## Phase 4: Mental Fitness Agent (OpenAI)

### 4.1 Create Mental Fitness Agent

- **File**: `backend/app/agents/mental_fitness_agent.py`
- **Extends**: `BaseAgent` (OpenAI)
- **Model**: Use OpenAI (same as Physical Fitness Agent)
- **System Prompt**: Specialized for mindfulness, stress management, mental wellness
- **Tools**:
- Inherit base tools
- Add `CreateMentalFitnessLogTool`
- Add web search tool for mental wellness resources

### 4.2 Create Mental Fitness Log Tool

- **File**: `backend/app/agents/base_agent.py`
- **Tool**: `CreateMentalFitnessLogTool` extending `BaseTool`
- **Fields**: activity_date, activity_type, duration_minutes, mood_before, mood_after, notes
- **Model**: Use `MentalFitnessLog` model

## Phase 5: Coordinator Agent

### 5.1 Create Coordinator Agent

- **File**: `backend/app/agents/coordinator_agent.py`
- **Extends**: `BaseAgent` (OpenAI)
- **Functionality**:
- **Query Routing**: Analyze user query and route to appropriate agent (Physical/Nutrition/Mental)
- **Holistic Planning**: Create cross-domain plans combining fitness + nutrition + mental wellness
- **Agent Orchestration**: Call other agents and synthesize responses
- **System Prompt**: 
- Understands when to route vs. create holistic plans
- Can coordinate multiple agents for comprehensive recommendations
- **Tools**: 
- Access to all three agents (Physical, Nutrition, Mental)
- Can create logs across all domains

### 5.2 Coordinator Logic Implementation

- **Routing Logic**: 
- Keyword detection for domain (fitness/nutrition/mental)
- Intent classification
- Route to appropriate agent or create holistic plan
- **Holistic Planning**:
- Call all three agents with coordinated queries
- Synthesize responses into unified plan
- Ensure consistency across domains

## Phase 6: API Routes

### 6.1 Add Nutrition Agent Endpoint

- **File**: `backend/app/routers/agents.py`
- **Endpoint**: `POST /agents/nutrition/chat`
- **Implementation**: Similar to physical-fitness endpoint, uses `NutritionAgent`

### 6.2 Add Mental Fitness Agent Endpoint

- **File**: `backend/app/routers/agents.py`
- **Endpoint**: `POST /agents/mental-fitness/chat`
- **Implementation**: Similar to physical-fitness endpoint, uses `MentalFitnessAgent`

### 6.3 Add Coordinator Agent Endpoint

- **File**: `backend/app/routers/agents.py`
- **Endpoint**: `POST /agents/coordinator/chat`
- **Implementation**: Uses `CoordinatorAgent` for routing/holistic planning

### 6.4 Add Log Endpoints

- **File**: `backend/app/routers/logs.py`
- **Endpoints**:
- `GET /logs/nutrition` - Get nutrition logs (pagination)
- `GET /logs/mental-fitness` - Get mental fitness logs (pagination)
- **Schemas**: Create in `backend/app/schemas/logs.py`

## Phase 7: Frontend Integration

### 7.1 Agent Selector Component

- **File**: `frontend/components/AgentSelector.jsx`
- **Functionality**: 
- Dropdown/buttons to select agent (Physical/Nutrition/Mental/Coordinator)
- Update chat endpoint based on selection
- Visual indicator of active agent

### 7.2 Update Dashboard

- **File**: `frontend/app/dashboard/page.js`
- **Changes**:
- Add agent selector to header
- Update API calls to use selected agent endpoint
- Store selected agent in state/localStorage

### 7.3 Log Display Updates

- **File**: `frontend/app/dashboard/page.js`
- **Changes**:
- Add tabs/sections for different log types (Workout/Nutrition/Mental)
- Display nutrition and mental fitness logs
- Update workout logs button to show all log types

## Phase 8: Schemas & Validation

### 8.1 Update Agent Schemas

- **File**: `backend/app/schemas/agents.py`
- **Changes**: Ensure `AgentChatRequest` and `AgentChatResponse` work for all agents

### 8.2 Create Log Schemas

- **File**: `backend/app/schemas/logs.py`
- **Add**:
- `NutritionLogResponse`
- `MentalFitnessLogResponse`
- `NutritionLogsListResponse`
- `MentalFitnessLogsListResponse`

## Phase 9: Environment Variables

### 9.1 Update .env.example

- **File**: `backend/.env.example`
- **Add**:
- `GOOGLE_GEMINI_API_KEY` - For Nutrition Agent
- `TAVILY_API_KEY` - For web search tool

## Phase 10: Testing & Documentation

### 10.1 Update Test Scripts

- **File**: `backend/test_agent.py`
- **Add**: Tests for Nutrition, Mental Fitness, and Coordinator agents

### 10.2 Update Documentation

- **Files**: `README.md`, `backend/README.md`, `SETUP_GUIDE.md`
- **Updates**: 
- Document new agents
- Document new API endpoints
- Update setup instructions for new API keys

## Implementation Order

1. **Database Models** (Phase 1) - Foundation for logging
2. **Web Search Tool** (Phase 2) - Useful for all agents
3. **Nutrition Agent** (Phase 3) - First new agent with **image analysis support**
4. **Mental Fitness Agent** (Phase 4) - Second new agent
5. **Coordinator Agent** (Phase 5) - Requires other agents to exist
6. **API Routes** (Phase 6) - Expose agents via API with **image upload support**
7. **Frontend Integration** (Phase 7) - User-facing features with **image upload UI**
8. **Schemas & Validation** (Phase 8) - Data validation including image handling
9. **Environment & Docs** (Phases 9-10) - Configuration and documentation

## Key Feature: Image-Based Calorie Tracking

**Nutrition Agent Image Analysis Flow:**

1. User uploads food image via frontend (drag-drop or file picker)
2. Frontend converts image to base64 and sends with chat message
3. Backend receives image, validates format/size
4. Nutrition Agent uses Gemini Vision API to analyze image:

- Identify food items
- Estimate portion sizes
- Calculate calories and macros (protein, carbs, fats)
- Suggest meal type (breakfast/lunch/dinner/snack)

5. Agent responds with nutrition analysis and can auto-create nutrition log
6. Frontend displays analysis results and allows user to confirm/log meal

## Key Files to Modify/Create

**New Files:**

- `backend/app/models/nutrition_log.py`
- `backend/app/models/mental_fitness_log.py`
- `backend/app/agents/nutrition_agent.py`
- `backend/app/agents/mental_fitness_agent.py`
- `backend/app/agents/coordinator_agent.py`
- `frontend/components/AgentSelector.jsx`

**Modified Files:**

- `backend/app/models/user.py` - Add relationships
- `backend/app/models/__init__.py` - Export new models
- `backend/app/agents/base_agent.py` - Add web search tool, nutrition/mental log tools
- `backend/app/routers/agents.py` - Add new endpoints
- `backend/app/routers/logs.py` - Add nutrition/mental log endpoints
- `backend/app/schemas/logs.py` - Add new log schemas
- `backend/requirements.txt` - Add Gemini and Tavily dependencies
- `backend/.env.example` - Add new API keys
- `frontend/app/dashboard/page.js` - Add agent selector and log tabs
- `frontend/lib/api.js` - Add new agent API methods

## Dependencies

- `google-generativeai` - For Gemini API
- `tavily-python` - For web search
- LangChain Google Generative AI integration
- Alembic migrations for new tables