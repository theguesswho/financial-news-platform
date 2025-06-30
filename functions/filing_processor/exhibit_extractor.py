# functions/filing_processor/exhibit_extractor.py

import requests
from bs4 import BeautifulSoup
import re

def extract_press_release(filing_url):
    """
    Manually downloads and parses an SEC filing to find and extract the text
    of the press release exhibit (EX-99.1).
    """
    print(f"Manually parsing filing: {filing_url}")
    
    # Standard headers to act like a browser
    headers = {'User-Agent': 'FinancialNewsPlatform e.h.arghand@gmail.com'}
    
    try:
        # Step 1: Download the main filing "index" page
        response = requests.get(filing_url, headers=headers)
        response.raise_for_status()
        # Use BeautifulSoup to parse the HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        exhibit_url = None
        
        # Step 2: Find the exhibit table in the HTML
        print("Searching for the exhibit table in the filing...")
        # SEC filing exhibit tables are usually identified by this summary text
        exhibit_table = soup.find('table', summary='Document Format Files')
        
        if exhibit_table:
            # Step 3: Loop through each row of the table
            for row in exhibit_table.find_all('tr'):
                cells = row.find_all('td')
                # A valid row has several cells; we check the 'Type' cell for our exhibit
                if len(cells) > 1 and cells[1].text.strip() == 'EX-99.1':
                    # We found the press release row! Now find the link in the next cell.
                    link_tag = cells[2].find('a')
                    if link_tag and link_tag.has_attr('href'):
                        # The link is relative, so we add the SEC base URL
                        exhibit_url = "https://www.sec.gov" + link_tag['href']
                        print(f"Found Press Release URL: {exhibit_url}")
                        break # Exit the loop once we've found it
        
        if not exhibit_url:
            print("Could not find a link for exhibit EX-99.1 in this filing.")
            return None
            
        # Step 4: Use the found URL to download the exhibit text itself
        print("Downloading the exhibit text...")
        exhibit_response = requests.get(exhibit_url, headers=headers)
        exhibit_response.raise_for_status()
        exhibit_soup = BeautifulSoup(exhibit_response.content, 'html.parser')
        
        # Get all the text from the body of the exhibit's HTML
        exhibit_text = exhibit_soup.body.get_text(separator='\n', strip=True)
        
        print("\n--- Successfully Extracted Press Release Text ---")
        print(exhibit_text[:1500] + "...")
        print("-------------------------------------------------")
        
        return exhibit_text
            
    except Exception as e:
        print(f"An error occurred: {e}")
        return None