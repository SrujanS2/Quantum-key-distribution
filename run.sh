#!/usr/bin/env bash
set -euo pipefail

python -V
echo "Installing requirements..."
pip install -r requirements.txt

echo "1) Train model (loads /mnt/data/key.csv or key.pickle)"
python train_qkd_model.py

echo "2) Generate SHAP explanations"
python explain_qkd_model.py

echo "3) Run Streamlit app (open http://localhost:8501)"
echo "To stop: Ctrl+C"
streamlit run app_streamlit.py
