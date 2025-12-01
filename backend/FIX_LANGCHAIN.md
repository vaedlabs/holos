# Fix LangChain Version Compatibility Issue

## Problem
The error `ImportError: cannot import name 'ModelProfileRegistry' from 'langchain_core.language_models'` indicates a version mismatch between `langchain-openai` and `langchain-core`.

## Solution

Run these commands to fix the compatibility issue:

```bash
cd backend
pip install --upgrade langchain-openai>=0.2.3
# OR reinstall all LangChain packages together:
pip install --upgrade langchain langchain-core langchain-openai langchain-community
```

## Verify Fix

After upgrading, test the import:

```bash
python3 -c "from langchain_openai import ChatOpenAI; print('✓ Import successful')"
```

## Alternative: Use Latest Compatible Versions

If the above doesn't work, try installing the latest compatible versions:

```bash
pip install --upgrade \
  langchain>=0.3.0 \
  langchain-core>=0.3.0 \
  langchain-openai>=0.2.3 \
  langchain-community>=0.3.0
```

Then run the test again:
```bash
python3 test_post_mvp_setup.py
```

