# create_cik_list.py

import requests
import json

def generate_cik_list():
    """
    Reads tickers from tickers.txt, downloads the master CIK mapping from the SEC,
    and creates a ciks.txt file containing the CIKs for our target tickers.
    """
    
    # --- Step 1: Read our master list of tickers ---
    try:
        with open('tickers.txt', 'r') as f:
            # Create a set of tickers for fast lookups
            target_tickers = {line.strip().upper() for line in f if line.strip()}
        print(f"Loaded {len(target_tickers)} target tickers from tickers.txt")
    except FileNotFoundError:
        print("Error: tickers.txt not found. Please create it first.")
        return

    # --- Step 2: Download the master CIK lookup file from the SEC ---
    # This URL points to a large JSON file containing all companies
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {'User-Agent': 'FinancialNewsPlatform e.h.arghand@gmail.com'}
    
    print(f"Downloading master CIK list from {url} ...")
    response = requests.get(url, headers=headers)
    response.raise_for_status() # Raise an error if the download fails
    
    # The SEC file is structured as: {"0": {"cik_str": ..., "ticker": ..., "title": ...}, ...}
    all_company_data = response.json()
    print("Master CIK list downloaded successfully.")

    # --- Step 3: Create a mapping of Ticker to CIK for easy searching ---
    print("Building Ticker-to-CIK map...")
    ticker_to_cik = {}
    for key, company_info in all_company_data.items():
        # The CIK needs to be padded with leading zeros to be 10 digits long
        ticker = company_info['ticker']
        cik = str(company_info['cik_str']).zfill(10)
        ticker_to_cik[ticker] = cik

    # --- Step 4: Find the CIKs for our target tickers and save them ---
    print("Finding CIKs for our target tickers and saving to ciks.txt...")
    found_ciks = set()
    for ticker in target_tickers:
        if ticker in ticker_to_cik:
            found_ciks.add(ticker_to_cik[ticker])
        else:
            print(f"Warning: Could not find CIK for ticker: {ticker}")
            
    # Save the found CIKs to our new file, one per line
    with open('ciks.txt', 'w') as f:
        for cik in sorted(list(found_ciks)): # Sort the CIKs before saving
            f.write(cik + '\n')
            
    print(f"\nSUCCESS: Found {len(found_ciks)} CIKs and saved them to ciks.txt")


if __name__ == "__main__":
    # This script is designed to be run once to generate our file.
    generate_cik_list()