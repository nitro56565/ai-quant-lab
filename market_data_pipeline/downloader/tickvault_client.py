"""
TickVault client for downloading market data from Dukascopy public feed.
"""

import requests
from datetime import datetime
import logging
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)

class TickVaultClient:
    """
    Client for downloading market data from Dukascopy's public historical data feed.
    No authentication required.
    """
    
    BASE_URL = "https://datafeed.dukascopy.com/datafeed"
    
    def __init__(self):
        """
        Initialize the TickVault client with connection pooling and retries.
        No authentication required for Dukascopy public feed.
        """
        self.session = requests.Session()
        
        # Sane browser headers to prevent Dukascopy rate limiting & connection drops
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        })
        
        # Configure retry strategy and connection pooling for concurrent requests
        retries = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(
            pool_connections=50,
            pool_maxsize=50,
            max_retries=retries
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

    
    def download_hourly_bi5(self, symbol, year, month, day, hour):
        """
        Download hourly BI5 file for a specific hour from Dukascopy.
        Implements jittered exponential backoff for temporary 503/429/connection drops.
        Returns raw BI5 bytes, or b'' if empty/404.
        """
        import time
        import random

        url = f"{self.BASE_URL}/{symbol}/{year}/{(month - 1):02d}/{day:02d}/{hour:02d}h_ticks.bi5"
        max_attempts = 5
        base_backoff = 1.0

        for attempt in range(1, max_attempts + 1):
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    return response.content
                elif response.status_code == 404:
                    # Permanent missing file (weekend/market closure) -> return empty immediately without retry
                    return b''
                elif response.status_code in (429, 503, 500, 502, 504):
                    if attempt < max_attempts:
                        sleep_time = base_backoff * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                        logger.debug(f"HTTP {response.status_code} throttling for {url} (attempt {attempt}/{max_attempts}). Retrying in {sleep_time:.2f}s...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        response.raise_for_status()
                else:
                    response.raise_for_status()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
                if attempt < max_attempts:
                    sleep_time = base_backoff * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                    logger.debug(f"Network drop ({e}) for {url} (attempt {attempt}/{max_attempts}). Retrying in {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue
                else:
                    logger.error(f"Failed to download {url} after {max_attempts} attempts: {e}")
                    raise

        return b''

