# Gemini API Implementation Fix

## Current Situation

1. **Your code uses `google.generativeai` directly** (correct approach for image analysis)
2. **Version conflicts** between `langchain-google-genai` and `google-generativeai`
3. **The Nutrition Agent** already uses the direct SDK correctly for images

## Solution: Use Direct SDK for Both Text and Images

Based on the official Google Generative AI Python SDK, we should use `google.generativeai` directly for both text and image responses, avoiding the LangChain wrapper for Gemini.

### Current Implementation (Image Analysis) - CORRECT
```python
import google.generativeai as genai

# Configure API key
genai.configure(api_key=os.getenv("GOOGLE_GEMINI_API_KEY"))

# Create model
model = genai.GenerativeModel('gemini-1.5-pro')

# For images: Pass PIL Image directly
response = model.generate_content([prompt, image])
```

### Text-Only Responses
```python
# Same approach for text-only
response = model.generate_content(prompt)
```

## Recommended Package Versions

Based on your environment and compatibility:

```txt
# Use direct SDK (no LangChain wrapper needed for Gemini)
google-generativeai>=0.8.5  # Latest stable version

# For LangChain integration (if needed for other agents)
langchain-core==1.1.0
langchain-openai==1.1.0
langchain-google-genai==2.0.10  # Only if you want LangChain integration
```

## Fix Strategy

1. **Keep using `google.generativeai` directly** for Nutrition Agent (already correct)
2. **Remove dependency on `langchain_google_genai`** from Nutrition Agent
3. **Use direct SDK for both text and image queries**
4. **Update requirements.txt** to reflect compatible versions

## API Key Usage

The API key is set via:
```python
import google.generativeai as genai
genai.configure(api_key=os.getenv("GOOGLE_GEMINI_API_KEY"))
```

This works for both text and image analysis - no different payload needed.

## Next Steps

1. Update Nutrition Agent to use direct SDK for all queries (text + image)
2. Remove `langchain_google_genai` import if not needed
3. Update requirements.txt with compatible versions
4. Test both text and image functionality

