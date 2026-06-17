import shap
import numpy as np
import logging

class QKDExplainer:
    def __init__(self, model, feature_names):
        """
        Initialize the SHAP TreeExplainer for the given model.
        """
        self.feature_names = feature_names
        self.explainer = None
        try:
            print("[XAI] Initializing SHAP Explainer...")
            # Initialize TreeExplainer
            # check_additivity=False allows it to run even if model output isn't exactly sum of shap values
            # (sometimes needed for certain sklearn versions/configurations)
            self.explainer = shap.TreeExplainer(model) 
            print("[XAI] SHAP Explainer ready.")
        except Exception as e:
            logging.warning(f"Could not initialize SHAP: {e}")

    def explain(self, X):
        """
        Calculate SHAP values for a single sample X (1, n_features)
        and return a human-readable string of top contributions.
        """
        if not self.explainer:
            return ""
        
        try:
            shap_vals = self.explainer.shap_values(X)
            vals = None
            
            # --- Robust SHAP Value Extraction ---
            # SHAP can return:
            # 1. List of arrays [ (N,F), (N,F) ] -> for binary classification (Class 0, Class 1)
            # 2. 3D Array (N, F, C) -> for multi-class or binary in newer versions
            # 3. 2D Array (N, F) -> for regression or single-output
            
            if isinstance(shap_vals, list):
                # Case 1: List. We usually want Class 1 (Attack)
                if len(shap_vals) > 1:
                    vals = shap_vals[1][0] # Class 1, Sample 0
                else:
                    vals = shap_vals[0][0] # Single output, Sample 0
            else:
                # Case 2 & 3: Numpy Array
                if len(shap_vals.shape) == 3:
                    # (N, F, C)
                    if shap_vals.shape[2] > 1:
                        vals = shap_vals[0, :, 1] # Class 1
                    else:
                        vals = shap_vals[0, :, 0]
                elif len(shap_vals.shape) == 2:
                    # (N, F)
                    vals = shap_vals[0]
            
            # --- Generate Explanation String ---
            if vals is not None and len(vals) == len(self.feature_names):
                # Friendly Names Mapping
                friendly_names = {
                    "QBER": "Quantum Error Rate",
                    "SignalIntensity": "Signal Strength",
                    "TimingJitter": "Timing Jitter",
                    "DetectorTemp": "Detector Temp"
                }

                # Pair features with their SHAP impact
                contribs = []
                for i, feat in enumerate(self.feature_names):
                    contribs.append((feat, vals[i]))
                
                # Sort by absolute magnitude (biggest impact first)
                contribs.sort(key=lambda x: abs(x[1]), reverse=True)
                
                # Take top 2 features
                top_items = []
                for feat, val in contribs[:2]: 
                    # Only show if impact is significant
                    if abs(val) < 0.01: continue
                    
                    fname = friendly_names.get(feat, feat)
                    direction = "High" if val > 0 else "Low" # Contextual guess, though RF is non-linear. 
                    # Actually SHAP sign indicates contribution to class 1 (Attack).
                    # Positive SHAP = Pushes towards Attack.
                    
                    top_items.append(f"{fname} (+{val:.2f} risk)")
                
                if top_items:
                    return " due to " + ", ".join(top_items)
            else:
                logging.warning(f"SHAP shape mismatch. Vals shape: {getattr(vals, 'shape', 'None')}")
                
        except Exception as e:
            logging.warning(f"SHAP calc failed: {e}")
            
        return ""
    def explain_structured(self, X):
        """
        Returns a dictionary of feature contributions for visualization.
        Format: {'feature': 'Name', 'impact': 0.5, 'risk_contribution': 'High/Low'}
        """
        if not self.explainer:
            return {}
        
        try:
            shap_vals = self.explainer.shap_values(X)
            vals = None
            
            # --- Robust SHAP Value Extraction (Same logic as above) ---
            if isinstance(shap_vals, list):
                if len(shap_vals) > 1: vals = shap_vals[1][0]
                else: vals = shap_vals[0][0]
            else:
                if len(shap_vals.shape) == 3:
                    if shap_vals.shape[2] > 1: vals = shap_vals[0, :, 1]
                    else: vals = shap_vals[0, :, 0]
                elif len(shap_vals.shape) == 2:
                    vals = shap_vals[0]
            
            if vals is not None and len(vals) == len(self.feature_names):
                friendly_names = {
                    "QBER": "Quantum Error Rate",
                    "SignalIntensity": "Signal Strength",
                    "TimingJitter": "Timing Jitter",
                    "DetectorTemp": "Detector Temp"
                }
                
                # Calculate total absolute impact for percentage
                total_impact = np.sum(np.abs(vals))
                if total_impact == 0: total_impact = 1.0
                
                data = []
                for i, feat in enumerate(self.feature_names):
                    impact = vals[i]
                    pct = (abs(impact) / total_impact) * 100
                    
                    data.append({
                        "id": feat,
                        "name": friendly_names.get(feat, feat),
                        "shap_value": float(impact),
                        "contribution_percent": float(round(pct, 1)),
                        "is_risk_factor": bool(impact > 0) # Positive pushes towards Attack
                    })
                
                # Sort by contribution percent
                data.sort(key=lambda x: x["contribution_percent"], reverse=True)
                return data
                
        except Exception as e:
            logging.warning(f"SHAP structured calc failed: {e}")
            
        return {}
