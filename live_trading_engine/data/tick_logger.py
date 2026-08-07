"""
Partitioned Append-Only Parquet Tick Logger v3.0.
Logs 100% of raw stream ticks into daily partitioned chunks (part_0001.parquet, part_0002.parquet).
Zero file rewrite overhead.
"""

import os
import pandas as pd
from datetime import datetime, timezone
import logging
from typing import Dict, Any, List

logger = logging.getLogger("PartitionedTickParquetLogger")

class PartitionedTickParquetLogger:
    """
    High-throughput append-only partition writer for raw tick streams.
    Saves daily chunks without reading or overwriting existing files.
    """
    def __init__(self, base_dir: str = "live_trading_engine/logs/ticks", chunk_size: int = 2000):
        self.base_dir = base_dir
        self.chunk_size = chunk_size
        self.buffer: List[Dict[str, Any]] = []
        self.part_counter: Dict[str, int] = {}
        os.makedirs(self.base_dir, exist_ok=True)

    def log_tick(self, tick: Dict[str, Any]):
        """
        Appends tick object to memory buffer and flushes when chunk_size is reached.
        """
        self.buffer.append(tick)
        if len(self.buffer) >= self.chunk_size:
            self.flush()

    def flush(self):
        """
        Flushes memory buffer into a new part_XXXX.parquet file under logs/ticks/{symbol}/{YYYY-MM-DD}/.
        """
        if not self.buffer:
            return
        try:
            df = pd.DataFrame(self.buffer)
            dt_str = pd.to_datetime(df['timestamp'].iloc[0]).strftime("%Y-%m-%d")
            symbol = str(df['symbol'].iloc[0]).upper()

            day_dir = os.path.join(self.base_dir, symbol, dt_str)
            os.makedirs(day_dir, exist_ok=True)

            if day_dir not in self.part_counter:
                existing = [f for f in os.listdir(day_dir) if f.startswith("part_") and f.endswith(".parquet")]
                self.part_counter[day_dir] = len(existing) + 1

            part_num = self.part_counter[day_dir]
            file_path = os.path.join(day_dir, f"part_{part_num:04d}.parquet")

            df.to_parquet(file_path, compression="snappy", index=False)
            self.part_counter[day_dir] += 1
            logger.debug(f"💾 Flushed {len(df)} ticks to {file_path}")
            self.buffer.clear()
        except Exception as e:
            logger.error(f"Error flushing tick parquet partition: {e}", exc_info=True)
