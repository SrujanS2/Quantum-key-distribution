# leakage_check.py
"""
Quick leakage check: for each feature, train a DecisionTree(max_depth=1) (stump)
to predict Label using only that feature and report metrics. If any single-feature
stump achieves high F1 (>= 0.95 by default), it flags possible leakage.

Usage:
    python leakage_check.py
Output:
    prints table and writes leakage_report.txt
"""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import classification_report, f1_score, accuracy_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
import joblib
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent / "dataset"))

DATA_LOADER = "data_loader"
THRESH_F1 = 0.95
OUTPATH = Path(__file__).resolve().parent / "leakage_report.txt"

def main():
    # import loader
    try:
        from data_loader import load_dataset
    except Exception as e:
        print("Cannot import data_loader: ", e)
        sys.exit(1)
    df = load_dataset()
    print("Loaded cleaned dataset shape:", df.shape)
    if df.shape[0] == 0:
        print("No rows to run leakage check.")
        return
    features = [c for c in df.columns if c not in ("Label", "_label_generated_by")]
    print("Features to test:", features)
    results = []
    X = df[features]
    y = df["Label"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y if len(np.unique(y))>1 else None)
    for f in features:
        Xt = X_train[[f]].fillna(0).values
        Xt_test = X_test[[f]].fillna(0).values
        clf = DecisionTreeClassifier(max_depth=1, random_state=42)
        clf.fit(Xt, y_train)
        yp = clf.predict(Xt_test)
        f1 = f1_score(y_test, yp, zero_division=0)
        acc = accuracy_score(y_test, yp)
        prec = precision_score(y_test, yp, zero_division=0)
        rec = recall_score(y_test, yp, zero_division=0)
        results.append((f, acc, prec, rec, f1))
        print(f"Feature: {f}  acc={acc:.4f} prec={prec:.4f} rec={rec:.4f} f1={f1:.4f}")
    # write report
    with OUTPATH.open("w") as fh:
        fh.write("Leakage check report\n")
        fh.write("====================\n\n")
        for row in results:
            fh.write(f"Feature: {row[0]}  acc={row[1]:.4f} prec={row[2]:.4f} rec={row[3]:.4f} f1={row[4]:.4f}\n")
        fh.write("\n\nFlagged features (f1 >= {:.2f}):\n".format(THRESH_F1))
        for row in results:
            if row[4] >= THRESH_F1:
                fh.write(f" - {row[0]}  f1={row[4]:.4f}\n")
    print("Saved leakage report to", OUTPATH)
    flagged = [r for r in results if r[4] >= THRESH_F1]
    if flagged:
        print("\nWARNING: Possible leakage detected. Features with f1 >= {:.2f}:".format(THRESH_F1))
        for r in flagged:
            print(" -", r[0], "f1=", r[4])
    else:
        print("\nNo single-feature leakage detected (threshold f1 >= {:.2f}).".format(THRESH_F1))

if __name__ == "__main__":
    main()
