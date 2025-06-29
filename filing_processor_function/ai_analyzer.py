# filing_processor_function/ai_analyzer.py (FINAL CORRECTED VERSION)

import os
import google.generativeai as genai

def analyze_text_with_gemini(text_to_analyze, market_context):
    """
    Analyzes filing text in the context of market data to generate an insightful snippet.
    """
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        return "Error: API Key not configured."

    # THIS IS THE FIX: We configure the library right before we use it,
    # not in the global scope.
    genai.configure(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    You are a neutral financial analyst for an objective newswire. Your task is to write a 2-5 sentence news snippet synthesizing the provided data points.
    Do not invent information or speculate on future stock prices.
    If the data points are contradictory (e.g., good news but stock is down), highlight the contradiction.
    If they are aligned (e.g., bad news and stock is down), suggest the correlation.

    DATA POINTS:
    - Primary Source (from company press release): "{text_to_analyze}"
    - Market Context: "{market_context}"

    Generate the news snippet based only on the data provided.
    """
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("Sending text and context to Gemini for synthesis...")
    response = model.generate_content(prompt)
    print("...Insight received from Gemini.")
    return response.text