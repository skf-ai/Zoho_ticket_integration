# Helper functions for logging, response formatting, etc.

import logging

def setup_logging():
    """Sets up basic logging."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
