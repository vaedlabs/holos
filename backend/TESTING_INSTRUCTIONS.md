# Testing Instructions

Current stack pinned in `backend/requirements.txt`:

- `langchain==1.1.0`
- `langchain-core==1.1.0`
- `langchain-openai==1.1.0`

Python 3.12+ recommended.

---

## If You're on the Current Stack

Just install from requirements and you should be fine:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Verify the imports worked:

```bash
python3 -c "from langchain_openai import ChatOpenAI; print('LangChain/OpenAI import successful')"
python3 -c "import langchain, langchain_core; print(langchain.__version__, langchain_core.__version__)"
```

Should print `1.1.0 1.1.0` with no errors. Then run the tests:

```bash
python3 test_post_mvp_setup.py
# or just: pytest
```

---

## What the Tests Check

1. Environment variables (`DATABASE_URL`, `OPENAI_API_KEY`, `GOOGLE_GEMINI_API_KEY`)
2. Database models (User, MedicalHistory, NutritionLog, MentalFitnessLog, etc.)
3. Base agent tools (GetMedicalHistoryTool, CreateNutritionLogTool, etc.)
4. Physical Fitness Agent
5. Nutrition Agent (needs `GOOGLE_GEMINI_API_KEY`)
6. Mental Fitness Agent
7. Python dependencies
8. Database connection and tables
9. Tool schema validation
10. Agent method structure

A clean run looks like:

```text
All models imported successfully
All base agent tools imported successfully
All agents imported successfully
All agent methods verified
```

---

## After a Clean Test

1. Double-check all env variables are set — especially `GOOGLE_GEMINI_API_KEY` for the Nutrition Agent
2. Make sure migrations are up to date: `python setup_database.py` or `alembic upgrade head`
3. You're good to go
