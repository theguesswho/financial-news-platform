# functions/filing_processor/ai_analyzer.py

import os
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def analyze_text_with_gemini(text_to_analyze, market_context):
    """
    Analyzes primary text (news or filing) in the context of market data 
    to generate an insightful snippet.
    """
    if not GEMINI_API_KEY:
        return "Error: GEMINI_API_KEY not configured."

    # --- THIS IS THE UPGRADED PROMPT ---
    prompt = f"""
    You are a concise, neutral financial analyst for an objective newswire. Your task is to write a 2-4 sentence news snippet synthesizing two data points: a piece of news and the latest stock market data.

    Your tone should be objective and factual, like a Reuters or Associated Press report. Do not use sensational language. Do not offer opinions or financial advice.

    DATA POINTS:
    1.  **Primary Information:** "{text_to_analyze}"
    2.  **Market Context:** "{market_context}"

    INSTRUCTIONS:
    - Synthesize these two data points into a single, coherent snippet.
    - If the news seems to align with the stock price data (e.g., bad news and the stock is down), state the correlation factually.
    - If the news contradicts the stock price data (e.g., good news but the stock is down), simply state both facts without speculating on the reason for the divergence.
    - If the market context is unavailable, state what the primary information says and note that market correlation could not be determined.
    - Focus only on the data provided. Do not invent information or speculate on future price movements.
    
    Generate the news snippet.
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("Sending primary text and market context to Gemini for synthesis...")
        response = model.generate_content(prompt)
        print("...Insight received from Gemini.")
        return response.text
    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return "AI analysis could not be completed due to an internal error."