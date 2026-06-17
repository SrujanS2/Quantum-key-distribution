import os
import pandas as pd
from pathlib import Path

def load_dataset(data_dir=None):
    """
    Loads all CSV files inside the data directory, concatenates them,
    and returns a cleaned/labeled Pandas DataFrame.
    """
    if data_dir is None:
        # Dynamically locate the data/ directory.
        # Since this data_loader.py sits in 'dataset/', the default data folder is:
        # dataset/data/
        current_dir = Path(__file__).resolve().parent
        data_dir = current_dir / "data"
        if not data_dir.exists():
            # Fallback for running from different directories
            data_dir = Path("dataset/data")
            if not data_dir.exists():
                data_dir = Path("data")

    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir.absolute()}")

    # Gather all CSV files under data_dir
    files = list(data_dir.glob("*.csv"))
    # Exclude any other CSV files that aren't the dataset (like logs)
    files = [f for f in files if f.name not in ("qkd_logs.csv", "device_chat_full_log.csv")]

    if not files:
        raise FileNotFoundError(f"No dataset CSV files found in: {data_dir.absolute()}")

    dfs = []
    for f in files:
        print(f"[data_loader] Loading: {f.name}")
        dfs.append(pd.read_csv(f))

    df = pd.concat(dfs, ignore_index=True)

    # Auto-label based on QBER threshold (median + 2 * std) if "Label" column is missing
    if "Label" not in df.columns:
        if "QBER" in df.columns:
            q = pd.to_numeric(df["QBER"], errors="coerce").dropna()
            if q.empty:
                df["Label"] = 0
            else:
                threshold = q.median() + 2 * (q.std(ddof=0) if q.std(ddof=0) > 0 else 0.0)
                df["Label"] = (pd.to_numeric(df["QBER"], errors="coerce") > threshold).astype(int)
                print(f"[data_loader] Generated 'Label' using QBER threshold: {threshold:.6f}")
        else:
            df["Label"] = 0

    return df
