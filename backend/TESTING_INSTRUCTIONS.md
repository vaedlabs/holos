# Testing Instructions - Post-MVP Phases 1-4

## Issue Found: LangChain Version Compatibility

The test revealed a version compatibility issue:
```
ImportError: cannot import name 'ModelProfileRegistry' from 'langchain_core.language_models'
```

## Fix Required

**Step 1: Upgrade langchain-openai**
```bash
cd backend
pip install --upgrade langchain-openai==0.2.3
```

**Step 2: Verify the fix**
```bash
python3 -c "from langchain_openai import ChatOpenAI; print('✓ Import successful')"
```

**Step 3: Run the full test**
```bash
python3 test_post_mvp_setup.py
```

## Alternative: Reinstall All LangChain Packages

If the above doesn't work, reinstall all LangChain packages together:
```bash
pip install --upgrade \
  langchain==0.3.0 \
  langchain-core==0.3.0 \
  langchain-openai==0.2.3 \
  langchain-community==0.3.0
```

## What the Test Checks

1. ✅ Environment variables (DATABASE_URL, API keys)
2. ✅ Database models (User, MedicalHistory, NutritionLog, MentalFitnessLog, etc.)
3. ✅ Base agent tools (GetMedicalHistoryTool, CreateNutritionLogTool, etc.)
4. ✅ Physical Fitness Agent
5. ✅ Nutrition Agent (requires GOOGLE_GEMINI_API_KEY)
6. ✅ Mental Fitness Agent
7. ✅ Python dependencies
8. ✅ Database connection and tables
9. ✅ Tool schema validation
10. ✅ Agent method structure

## Expected Results After Fix

Once `langchain-openai` is upgraded, all imports should work and you should see:
- ✓ All models imported successfully
- ✓ All base agent tools imported successfully
- ✓ All agents imported successfully
- ✓ All agent methods verified

## Next Steps After Successful Test

1. Ensure all environment variables are set (especially GOOGLE_GEMINI_API_KEY for Nutrition Agent)
2. Run database migrations if tables are missing
3. Proceed to Phase 5: Coordinator Agent

