# logs_parser.py
"""
Simple parser for logs.log to extract lines that mention SNU, excess_noise, secret_key_rate, or similar.
Appends parsed numeric metrics back into a DataFrame by index if timestamp or index is present.
This is heuristic — adjust to your log format.
"""

import re
from pathlib import Path
import pandas as pd

LOG_PATH = Path("/mnt/data/logs.log")

def parse_log_file(path: Path = LOG_PATH):
    if not path.exists():
        print(f"No log file at {path}")
        return []

    entries = []
    pattern = re.compile(r"(?P<key>\w+)\s*[:=]\s*(?P<val>[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    # we'll scan each line for numeric key:value pairs
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        matches = dict(pattern.findall(line))
        if matches:
            matches["_line"] = line.strip()
            matches["_lineno"] = lineno
            entries.append(matches)
    return entries

def entries_to_df(entries):
    if not entries:
        return pd.DataFrame()
    df = pd.DataFrame(entries)
    # convert numeric columns to float
    for c in df.columns:
        if c.startswith("_"):
            continue
        try:
            df[c] = pd.to_numeric(df[c], errors="ignore")
        except Exception:
            pass
    return df

if __name__ == "__main__":
    entries = parse_log_file()
    df = entries_to_df(entries)
    if df.empty:
        print("No numeric key:value pairs found in logs.log.")
    else:
        print("Parsed log entries (sample):")
        print(df.head(10))
        df.to_csv("/mnt/data/parsed_logs.csv", index=False)
        print("Saved /mnt/data/parsed_logs.csv")
