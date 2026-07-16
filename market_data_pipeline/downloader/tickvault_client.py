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
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            year: Year (e.g., 2018)
            month: Month (1-12)
            day: Day (1-31)
            hour: Hour (0-23)
            
        Returns:
            Raw BI5 file content as bytes
        """
        # Dukascopy URL format for historical tick data.
        # Note: Dukascopy month format is 0-indexed (00 = Jan, 11 = Dec).
        url = f"{self.BASE_URL}/{symbol}/{year}/{(month - 1):02d}/{day:02d}/{hour:02d}h_ticks.bi5"

        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {symbol} for {year}-{month:02d}-{day:02d} {hour:02d}:00: {e}")
            raise
    
    def download_data(self, symbol, start_date, end_date):
        """
        Download data for a symbol between dates.
        
        Args:
            symbol: Trading symbol
            start_date: Start date for data (datetime)
            end_date: End date for data (datetime)
            
        Returns:
            Downloaded market data
        """
        pass
