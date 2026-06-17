# explain_qkd_model.py
"""
SHAP explanation script for the 4-feature model.
Saves:
 - shap_summary.png
 - shap_force_sample.html
"""

import joblib, numpy as np, pandas as pd, shap, matplotlib.pyplot as plt
from pathlib import Path
import sys

MODEL_PATH = "qkd_rf_model.joblib"
OUTPUT_SUMMARY = "shap_summary.png"
OUTPUT_FORCE = "shap_force_sample.html"

# sample sizes (reduce if RAM limited)
BG_SIZE = 2000
SAMPLE_SIZE = 2000

def load_artifact(path=MODEL_PATH):
    if not Path(path).exists():
        raise FileNotFoundError("Model artifact not found. Train model first.")
    obj = joblib.load(path)
    if not isinstance(obj, dict) or "model" not in obj or "scaler" not in obj or "features" not in obj:
        raise RuntimeError("Model artifact missing expected keys.")
    return obj

def load_data():
    try:
        from data_loader import load_dataset
        df = load_dataset()
        print("Loaded cleaned dataset via data_loader:", df.shape)
        return df
    except Exception as e:
        # try raw CSV
        p = Path("data")/"key.csv"
        if p.exists():
            df = pd.read_csv(p, dtype=object)
            print("Loaded raw CSV:", df.shape)
            return df
        raise RuntimeError("No usable dataset for explanation.")

def build_Xs(df, features, scaler):
    Xdf = pd.DataFrame(index=df.index)
    for f in features:
        Xdf[f] = pd.to_numeric(df[f], errors="coerce") if f in df.columns else 0.0
    Xdf = Xdf.fillna(0.0)
    X = Xdf.values
    try:
        Xs = scaler.transform(X)
    except Exception as e:
        print("Scaler.transform failed:", e)
        Xs = X
    return Xs, Xdf

def main():
    obj = load_artifact()
    model, scaler, features = obj["model"], obj["scaler"], obj["features"]
    print("Model features:", features)

    df = load_data()
    Xs_full, Xdf_full = build_Xs(df, features, scaler)
    n = Xs_full.shape[0]
    print("Full Xs shape:", Xs_full.shape)

    # choose background and sample indices
    rng = np.random.default_rng(42)
    bg_idx = rng.choice(n, size=min(BG_SIZE, n), replace=False)
    sample_idx = rng.choice(n, size=min(SAMPLE_SIZE, n), replace=False)
    Xs_bg = Xs_full[bg_idx]
    Xs_sample = Xs_full[sample_idx]

    # wrapper returning attack probability
    def predict_attack_prob(x):
        try:
            proba = model.predict_proba(x)
            if proba.ndim == 1:
                return proba
            if proba.shape[1] > 1:
                return proba[:,1]
            return proba[:,0]
        except Exception as e:
            # fallback: raw predict
            p = model.predict(x)
            return p

    # create Explainer
    print("Creating shap.Explainer with background ...")
    explainer = shap.Explainer(predict_attack_prob, Xs_bg, feature_names=features)

    print("Computing SHAP on sample ...")
    shap_exp = explainer(Xs_sample)
    vals = shap_exp.values
    if isinstance(vals, np.ndarray) and vals.ndim == 2:
        print("SHAP values shape:", vals.shape)
        plt.figure(figsize=(8,6))
        shap.summary_plot(vals, Xs_sample, feature_names=features, show=False)
        plt.tight_layout()
        plt.savefig(OUTPUT_SUMMARY, dpi=200)
        plt.close()
        print("Saved", OUTPUT_SUMMARY)
    else:
        print("Unexpected shap values shape/type:", type(vals), getattr(vals, "shape", None))

    # select a single sample for force plot: highest predicted attack prob
    try:
        probs = predict_attack_prob(Xs_full)
        idx_attack = int(np.argmax(probs))
    except Exception:
        idx_attack = 0
    print("Selected sample index for force plot:", idx_attack)
    shap_single = explainer(Xs_full[idx_attack:idx_attack+1])
    single_vals = shap_single.values
    if isinstance(single_vals, np.ndarray) and single_vals.ndim == 2 and single_vals.shape[0] == 1:
        ev = shap_single.base_values
        ev_val = ev if np.isscalar(ev) else (ev[0] if len(ev)>0 else ev)
        fp = shap.force_plot(ev_val, single_vals[0], Xdf_full.iloc[idx_attack:idx_attack+1].values[0], feature_names=features)
        shap.save_html(OUTPUT_FORCE, fp)
        print("Saved", OUTPUT_FORCE)
    else:
        print("Could not create force plot: unexpected single shap values shape:", getattr(single_vals, "shape", None))

if __name__ == "__main__":
    main()
