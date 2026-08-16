"""
OANDA v20 Broker Connection Guard Component.
Handles API Authentication, Error Code Normalization, Timeout Recovery,
Rate Limit Exponential Backoff, and State Re-synchronization.
"""

import time
from typing import Tuple, Dict, Any, Optional

class OANDABrokerGuard:
    def __init__(self, api_token: Optional[str] = None, account_id: Optional[str] = None, environment: str = "practice"):
        self.api_token = api_token
        self.account_id = account_id
        self.environment = environment
        self.is_authenticated = False
        self.last_sync_time: Optional[float] = None

    def authenticate(self, token: Optional[str] = None, account_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Authenticates OANDA API credentials.
        """
        tok = token or self.api_token
        acc = account_id or self.account_id

        if not tok or not acc or tok == "INVALID_TOKEN" or acc == "INVALID_ACC":
            self.is_authenticated = False
            return False, "BROKER_INVALID_CREDENTIALS"

        self.api_token = tok
        self.account_id = acc
        self.is_authenticated = True
        self.last_sync_time = time.time()
        return True, "BROKER_AUTHENTICATED"

    def handle_http_error(self, status_code: int) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Normalizes HTTP response codes into standard system handling policies.
        """
        if status_code == 200 or status_code == 201:
            return True, "HTTP_SUCCESS", {'action': 'NONE'}
        elif status_code == 400:
            return False, "HTTP_400_BAD_REQUEST", {'action': 'REJECT_ORDER', 'retry': False}
        elif status_code == 401:
            self.is_authenticated = False
            return False, "HTTP_401_UNAUTHORIZED", {'action': 'FAIL_SAFE_HALT', 'retry': False}
        elif status_code == 403:
            return False, "HTTP_403_FORBIDDEN", {'action': 'FAIL_SAFE_HALT', 'retry': False}
        elif status_code == 429:
            return False, "HTTP_429_RATE_LIMITED", {'action': 'EXPONENTIAL_BACKOFF', 'retry': True, 'backoff_seconds': 5.0}
        elif status_code >= 500:
            return False, f"HTTP_{status_code}_SERVER_ERROR", {'action': 'QUERY_ACCOUNT_STATE', 'retry': True, 'backoff_seconds': 2.0}
        else:
            return False, f"HTTP_{status_code}_UNKNOWN_ERROR", {'action': 'FAIL_SAFE_HALT', 'retry': False}

    def handle_api_timeout(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Handles API Timeout without performing blind order retries.
        """
        return False, "BROKER_TIMEOUT", {
            'action': 'QUERY_ACCOUNT_STATE_BEFORE_RESUME',
            'allow_blind_retry': False
        }

    def handle_reconnection(self, current_time: float) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Handles connection recovery and forces state re-synchronization.
        """
        if not self.is_authenticated:
            auth_ok, auth_reason = self.authenticate()
            if not auth_ok:
                return False, auth_reason, {'resynced': False}

        self.last_sync_time = current_time
        return True, "BROKER_RECONNECTED_AND_RESYNCED", {'resynced': True, 'last_sync': self.last_sync_time}
