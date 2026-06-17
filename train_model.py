"""
TRAIN MODEL FOR QKD SYSTEM
- Auto-detects CSV files under ./data (any number)
- Creates Label from QBER threshold and trains RandomForest
- Saves model to qkd_rf_model.joblib
"""

import os
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier

REQUIRED = ["QBER", "SignalIntensity", "TimingJitter", "DetectorTemp"]
DATA_DIR = "data"
MODEL_PATH = "qkd_rf_model.joblib"

def load_all():
    if not os.path.isdir(DATA_DIR):
        raise FileNotFoundError(f"Data directory not found: {DATA_DIR}")
    files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv")]
    if not files:
        raise FileNotFoundError(f"No CSV files found in {DATA_DIR}")
    dfs = []
    for f in files:
        print(f"[OK] Loading: {f}")
        dfs.append(pd.read_csv(f))
    df = pd.concat(dfs, ignore_index=True)
    return df

def main():
    print("\n=== TRAINING RANDOM FOREST ===")
    df = load_all()

    # Auto-label based on QBER threshold (median + 2*std)
    q = df["QBER"].dropna()
    if q.empty:
        df["Label"] = 0
    else:
        threshold = q.median() + 2 * (q.std(ddof=0) if q.std(ddof=0) > 0 else 0.0)
        df["Label"] = (df["QBER"] > threshold).astype(int)
        print(f"[INFO] QBER threshold used -> {threshold:.6g}")

    X = df[REQUIRED].astype(float).fillna(0.0).values
    y = df["Label"].astype(int).values

    clf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)
    clf.fit(X, y)
    joblib.dump(clf, MODEL_PATH)
    print(f"[OK] Model trained and saved to {MODEL_PATH}")

if __name__ == "__main__":
    main()
