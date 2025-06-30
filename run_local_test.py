# run_local_test.py

import os
import sys
from unittest.mock import Mock

# This is a bit of a trick to make sure our scripts can find their modules
# It adds the 'functions' directory to the Python path
sys.path.append(os.path.abspath('functions'))

def run_test():
    """
    This function manually triggers our data-gathering and processing functions
    for local testing purposes.
    """
    print("--- Starting Local Test Run ---")

    # Mock event and context objects, as the functions expect them
    mock_event = {}
    mock_context = Mock()
    mock_context.event_id = 'local-test-run'

    # --- Step 1: Run the EOD Logger to ensure we have recent prices ---
    print("\n[1/3] Running FMP EOD Logger...")
    try:
        from fmp_eod_logger.main import run_fmp_eod_logger
        run_fmp_eod_logger(mock_event, mock_context)
        print("...EOD Logger finished.")
    except Exception as e:
        print(f"ERROR in EOD Logger: {e}")


    # --- Step 2: Run the RSS Aggregator to find news and trigger analysis ---
    # This will find news and publish messages to the Pub/Sub topic.
    # The LIVE filing_processor will pick these up.
    print("\n[2/3] Running RSS Aggregator...")
    try:
        from rss_aggregator.main import run_rss_aggregator
        run_rss_aggregator(mock_event, mock_context)
        print("...RSS Aggregator finished.")
    except Exception as e:
        print(f"ERROR in RSS Aggregator: {e}")

    print("\n[3/3] Local test run finished.")
    print("The RSS Aggregator has sent messages to your cloud Pub/Sub topic.")
    print("Your LIVE 'filing_processor' function in Google Cloud should now process them.")
    print("Wait about a minute, then check the UI for new reports.")


if __name__ == "__main__":
    # We need to make sure the environment variables are loaded
    if not os.getenv("DB_PASSWORD"):
        print("ERROR: Environment variables are not loaded.")
        print("Please run 'export $(grep -v '^#' .env | xargs)' in your terminal first.")
    else:
        run_test()