"""
Configuration Loader Module.
Loads and validates config.yaml settings for the live trading engine.
"""

import os
import yaml
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

class ConfigLoader:
    def __init__(self, config_path: str = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.raw_config = self._load_yaml()
        self.snapshot_path = self._create_immutable_config_snapshot()

    def _load_yaml(self) -> dict:
        if not os.path.exists(self.config_path):
            logger.warning(f"⚠️ Config file '{self.config_path}' not found. Using defaults.")
            return {}
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error parsing YAML config: {e}")
            return {}

    def _create_immutable_config_snapshot(self) -> str:

        """
        Creates an immutable YAML configuration snapshot upon engine startup.
        """
        try:
            from datetime import datetime, timezone
            snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "config_snapshots")
            os.makedirs(snapshot_dir, exist_ok=True)
            ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            snap_file = os.path.join(snapshot_dir, f"run_{ts_str}_config.yaml")

            with open(snap_file, "w") as f:
                yaml.dump(self.raw_config, f)
            logger.info(f"📸 Immutable Configuration Snapshot created at '{snap_file}'")
            return snap_file
        except Exception as e:
            logger.warning(f"Failed to create config snapshot: {e}")
            return ""


    @property
    def system(self) -> dict:
        return self.raw_config.get("system", {})

    @property
    def broker(self) -> dict:
        return self.raw_config.get("broker", {})

    @property
    def risk(self) -> dict:
        return self.raw_config.get("risk", {})

    @property
    def models(self) -> dict:
        return self.raw_config.get("models", {})

    @property
    def database(self) -> dict:
        return self.raw_config.get("database", {})

    @property
    def monitoring(self) -> dict:
        return self.raw_config.get("monitoring", {})

    @property
    def scheduler(self) -> dict:
        return self.raw_config.get("scheduler", {})

_config_instance = None

def get_config(config_path: str = None) -> ConfigLoader:
    global _config_instance
    if _config_instance is None or config_path is not None:
        _config_instance = ConfigLoader(config_path)
    return _config_instance
