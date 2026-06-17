import joblib
import sklearn
import numpy as np

try:
    clf = joblib.load("qkd_rf_model.joblib")
    print(f"Model type: {type(clf)}")
    if hasattr(clf, "n_features_in_"):
        print(f"n_features_in_: {clf.n_features_in_}")
    else:
        print("n_features_in_ attribute missing")
        
    if hasattr(clf, "feature_names_in_"):
        print(f"feature_names_in_: {clf.feature_names_in_}")
    
    # Check classes
    if hasattr(clf, "classes_"):
        print(f"classes_: {clf.classes_}")

except Exception as e:
    print(f"Error loading model: {e}")
