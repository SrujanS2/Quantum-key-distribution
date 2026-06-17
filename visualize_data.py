# visualize_data.py (updated, robust)
"""
Visualize dataset and message logs (robust to missing scikit-learn/scipy).
- Produces histograms and scatter-matrix sample.
- Computes class balance and feature means-by-class.
- Attempts to load model feature importances, but if joblib/scikit-learn import fails,
  it logs a message and continues without crashing.
- If message log CSV contains shap_values, it tries to parse and plot mean |SHAP| per feature.
"""

import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import ast
import traceback

DATA_DIR = Path("data")
CSV_PATH = Path("/mnt/data/key.csv") if Path("/mnt/data/key.csv").exists() else DATA_DIR / "key.csv"
LOG_CSV = DATA_DIR / "device_chat_full_log.csv"
MODEL_PATH = Path("qkd_rf_model.joblib")

FEATURES = ["QBER","SignalIntensity","TimingJitter","DetectorTemp"]

def safe_load_joblib(path):
    """
    Try to load a joblib file but do not crash the caller if scikit-learn or scipy is missing.
    Returns the loaded object or None on failure. Prints helpful diagnostics.
    """
    try:
        import joblib
    except Exception as e:
        print("joblib import failed (skipping model load). To enable model import, run:")
        print("  pip install joblib scikit-learn scipy")
        print("Import error:", e)
        return None

    try:
        obj = joblib.load(path)
        return obj
    except Exception as e:
        print("joblib.load failed. This often means scikit-learn/scipy are not importable in this venv.")
        print("If you want feature importances, install scikit-learn & scipy and re-run the script.")
        print("Load error:", repr(e))
        # print a short traceback for debugging (no huge unwinding)
        traceback.print_exc(limit=3)
        return None

def main():
    print("Loading dataset:", CSV_PATH)
    if not CSV_PATH.exists():
        print("Dataset not found at", CSV_PATH)
        return
    df = pd.read_csv(CSV_PATH, low_memory=False)
    print("Rows:", len(df))

    # generate labels if missing (same rule used earlier)
    if "Label" not in df.columns:
        q = pd.to_numeric(df["QBER"], errors="coerce").dropna()
        med = q.median()
        std = q.std(ddof=0)
        thr = med + 2*std
        df["Label"] = (pd.to_numeric(df["QBER"], errors="coerce") > thr).astype(int)
        print("Generated Label with QBER threshold:", thr)

    # Basic histograms
    try:
        df[FEATURES].hist(bins=50, figsize=(12,8))
        plt.suptitle("Feature distributions")
        plt.tight_layout()
        plt.show()
    except Exception as e:
        print("Could not draw histograms:", e)

    # scatter sample for pairwise (safe sampling)
    try:
        sample = df.sample(n=min(2000,len(df)), random_state=42)
        pd.plotting.scatter_matrix(sample[FEATURES], figsize=(10,10))
        plt.suptitle("Feature scatter matrix (sampled)")
        plt.show()
    except Exception as e:
        print("Could not draw scatter matrix:", e)

    # class counts
    print("\nClass distribution:\n", df["Label"].value_counts())
    print("\nClass percentages:\n", (df["Label"].value_counts(normalize=True)*100).round(6))
    print("\nFeature means by class:\n", df.groupby("Label")[FEATURES].mean())

    # Feature importances (if model present)
    if MODEL_PATH.exists():
        print("\nAttempting to load model artifact for feature importances...")
        art = safe_load_joblib(MODEL_PATH)
        if art is not None:
            try:
                clf = art.get("model") if isinstance(art, dict) else art
                feat_names = art.get("features") if isinstance(art, dict) and art.get("features") is not None else FEATURES
                # try to get feature_importances_ attr
                importances = None
                if hasattr(clf, "feature_importances_"):
                    importances = clf.feature_importances_
                elif hasattr(clf, "coef_"):
                    # linear models
                    importances = np.abs(clf.coef_).ravel()
                if importances is not None:
                    print("Feature importances:", dict(zip(feat_names, importances.tolist() if hasattr(importances,'tolist') else importances)))
                    try:
                        plt.figure(figsize=(6,4))
                        plt.bar(feat_names, importances)
                        plt.title("Feature importances (model)")
                        plt.show()
                    except Exception as e:
                        print("Could not plot feature importances:", e)
                else:
                    print("Model loaded but no feature_importances_ or coef_ found.")
            except Exception as e:
                print("Failed to extract feature importances from model artifact:", e)
                traceback.print_exc(limit=3)
        else:
            print("Skipping model-based importances due to joblib/model load failure.")
    else:
        print("\nNo model artifact found at", MODEL_PATH)

    # SHAP summary if present in log CSV
    if LOG_CSV.exists():
        print("\nFound log CSV at", LOG_CSV)
        logs = pd.read_csv(LOG_CSV, low_memory=False)
        if "shap_values" in logs.columns and logs["shap_values"].notna().any():
            print("Parsing SHAP values from logs (this may take memory/time)...")
            # shap column may contain stringified Python lists; handle robustly
            def parse_shap_cell(x):
                if pd.isna(x):
                    return None
                if isinstance(x, (list, tuple, np.ndarray)):
                    return np.asarray(x, dtype=float)
                if isinstance(x, str):
                    try:
                        val = ast.literal_eval(x)
                        return np.asarray(val, dtype=float)
                    except Exception:
                        try:
                            # fallback: comma-separated numbers
                            parts = [float(p) for p in x.strip().split(",") if p.strip()!='']
                            return np.asarray(parts, dtype=float)
                        except Exception:
                            return None
                return None

            vals = logs["shap_values"].apply(parse_shap_cell)
            vals = vals.dropna()
            if len(vals) == 0:
                print("No parsable shap_values found in log CSV.")
            else:
                arr = np.vstack(vals.values)
                mean_abs = np.mean(np.abs(arr), axis=0)
                # determine names: try to read from model artifact if loaded earlier
                try:
                    feat_names = art.get("features") if art is not None and isinstance(art, dict) and art.get("features") is not None else FEATURES
                except Exception:
                    feat_names = FEATURES
                print("Mean absolute SHAP per feature:", dict(zip(feat_names, mean_abs)))
                try:
                    plt.figure(figsize=(6,4))
                    plt.bar(feat_names, mean_abs)
                    plt.title("Mean |SHAP| per feature (from logs)")
                    plt.show()
                except Exception as e:
                    print("Could not plot SHAP summary:", e)
        else:
            print("No shap_values present in log CSV.")
    else:
        print("\nNo log CSV found at", LOG_CSV)

if __name__ == "__main__":
    main()
