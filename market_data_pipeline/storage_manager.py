import os
import json
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("StorageManager")

class StorageManager:
    """
    Manages structured storage for raw and processed market data under market_data_pipeline/:
      • Raw Ticks:       market_data_pipeline/downloads/raw/dukascopy/{symbol}/tick/{year}/
      • Versioned OHLC: market_data_pipeline/output/processed/v1/{symbol}/{timeframe}/{year}.parquet
      • DataLoader OHLC: market_data_pipeline/output/{symbol}/{timeframe}/{year}.parquet
      • Audit Metadata:  market_data_pipeline/metadata/{symbol}/symbol_info.json & audit_metadata.json
    """
    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
        self.pipeline_dir = base_dir / 'market_data_pipeline'
        self.downloads_dir = self.pipeline_dir / 'downloads'
        self.output_dir = self.pipeline_dir / 'output'
        self.metadata_dir = self.pipeline_dir / 'metadata'

    def get_raw_tick_dir(self, symbol: str, provider: str = "dukascopy", year: Optional[int] = None) -> Path:
        """Return path for immutable raw tick data."""
        symbol = symbol.upper().strip()
        p = self.downloads_dir / 'raw' / provider.lower() / symbol / 'tick'
        if year:
            p = p / str(year)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_versioned_output_dir(self, symbol: str, timeframe: str, version: str = "v1") -> Path:
        """Return path for versioned processed candle output."""
        symbol = symbol.upper().strip()
        p = self.output_dir / 'processed' / version / symbol / timeframe.lower()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_dataloader_output_dir(self, symbol: str, timeframe: str) -> Path:
        """Return path compatible with DataLoader (e.g. output/XAUUSD/bars/1h/)."""
        symbol = symbol.upper().strip()
        tf_norm = "1min" if timeframe.lower() in ("1m", "1min") else timeframe.lower()
        p = self.output_dir / symbol / "bars" / tf_norm
        p.mkdir(parents=True, exist_ok=True)
        return p


    def get_metadata_dir(self, symbol: str) -> Path:
        """Return path for symbol metadata."""
        symbol = symbol.upper().strip()
        p = self.metadata_dir / symbol
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_processed_candles(self, df_candles: pd.DataFrame, symbol: str, timeframe: str, year: int, version: str = "v1"):
        """Write processed candles to both versioned and DataLoader output paths."""
        v_dir = self.get_versioned_output_dir(symbol, timeframe, version)
        dl_dir = self.get_dataloader_output_dir(symbol, timeframe)

        v_file = v_dir / f"{year}.parquet"
        dl_file = dl_dir / f"{year}.parquet"

        df_candles.to_parquet(v_file)
        df_candles.to_parquet(dl_file)
        logger.info(f"Saved {symbol} {timeframe} ({len(df_candles)} rows) to {v_file} and {dl_file}")

    def save_audit_metadata(self, symbol: str, metadata_dict: Dict[str, Any]):
        """Save symbol_info.json and audit_metadata.json."""
        m_dir = self.get_metadata_dir(symbol)
        
        # Save symbol_info.json for DataLoader
        sym_info_file = m_dir / "symbol_info.json"
        sym_info = {
            "symbol": symbol,
            "digits": 2 if "JPY" in symbol or "XAU" in symbol else 5,
            "pip_size": 0.01 if "JPY" in symbol or "XAU" in symbol else 0.0001,
            "timeframe_supported": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
            "data_source": metadata_dict.get("provider", "Dukascopy")
        }
        with open(sym_info_file, 'w') as f:
            json.dump(sym_info, f, indent=2)

        # Save audit_metadata.json
        audit_file = m_dir / "audit_metadata.json"
        with open(audit_file, 'w') as f:
            json.dump(metadata_dict, f, indent=2)

        logger.info(f"Saved metadata for {symbol} to {m_dir}")
