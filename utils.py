# utils.py (Corrected Version)

import os
import requests
import json

# --- SETTINGS ---
FMP_API_KEY = os.getenv("FMP_API_KEY")
TICKER_FILE = "tickers.txt"
OUTPUT_FILE = "company_map.json"

def create_company_map_from_list():
    """
    Reads our curated list of tickers, finds their official company names via the FMP API,
    and saves the result to a new mapping file.
    """
    if not FMP_API_KEY:
        print("Error: FMP_API_KEY environment variable must be set.")
        return

    # Step 1: Read OUR curated list of tickers.
    try:
        with open(TICKER_FILE, 'r') as f:
            target_tickers = {line.strip().upper() for line in f if line.strip()}
        print(f"Loaded {len(target_tickers)} target tickers from {TICKER_FILE}")
    except FileNotFoundError:
        print(f"Error: {TICKER_FILE} not found. Please restore your curated list first.")
        return

    # Step 2: Get ALL stocks from FMP to build a temporary lookup map.
    all_stocks_url = f"https://financialmodelingprep.com/api/v3/stock/list?apikey={FMP_API_KEY}"
    print("Downloading master stock list from FMP to build a lookup table...")
    response = requests.get(all_stocks_url)
    response.raise_for_status()
    all_stocks = response.json()
    ticker_to_name_lookup = {s['symbol']: s['name'] for s in all_stocks if s.get('symbol')}
    print("Lookup table created.")

    # Step 3: Create our final map using only the tickers from our list.
    final_company_map = {}
    for ticker in sorted(list(target_tickers)):
        if ticker in ticker_to_name_lookup:
            final_company_map[ticker] = ticker_to_name_lookup[ticker]
        else:
            print(f"Warning: Could not find a company name for ticker: {ticker}")
    
    # Step 4: Save the result to a NEW file.
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(final_company_map, f, indent=4)
        
    print(f"\nSUCCESS: Created {OUTPUT_FILE} with {len(final_company_map)} company mappings.")


if __name__ == "__main__":
    create_company_map_from_list()