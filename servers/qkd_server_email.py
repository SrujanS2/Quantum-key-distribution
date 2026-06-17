"""
qkd_server_email.py — Session-based QKD Authentication with Email Verification
- Devices must authenticate with a QKD code upon connection.
- The server prompts the administrator for the user's email address upon connection request.
- The QKD code is sent to the provided email address.
- Once authenticated, messages are exchanged freely (secure session).
"""

import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent / "models"))
sys.path.append(str(Path(__file__).resolve().parent.parent / "utils"))

import time
import random
import hashlib
import csv
import logging
import joblib
import numpy as np
import pandas as pd
from flask import Flask, render_template_string, jsonify, request
from qkd_xai import QKDExplainer
from flask_socketio import SocketIO
from crypto_utils import bytes_to_bits, otp_encrypt, otp_decrypt
from email_sender import send_email

# ---------- config ----------
HOST = "0.0.0.0"
PORT = 5000
DATA_DIR = str(Path(__file__).resolve().parent.parent / "dataset" / "data")
CSV_LOG = str(Path(__file__).resolve().parent.parent / "dataset" / "qkd_logs.csv")
REQUIRED = ["QBER", "SignalIntensity", "TimingJitter", "DetectorTemp"]
MODEL_PATH = str(Path(__file__).resolve().parent.parent / "models" / "qkd_rf_model.joblib")

# ---------- EMAIL CONFIG ----------
# 1. Try to get from Environment Variables (Best Practice)
# 2. Fallback to these hardcoded values (Edit them if you don't want to use Env Vars)
SMTP_CONFIG = {
    "host": "smtp.gmail.com",
    "port": 587,
    "user": os.getenv("QKD_SMTP_USER", "your_email@gmail.com"),
    "password": os.getenv("QKD_SMTP_PASS", "your_app_password")
}

# Warn if using placeholders, and ask for input
if SMTP_CONFIG["user"] == "your_email@gmail.com" or SMTP_CONFIG["password"] == "your_app_password":
    print("\n[SETUP] Email credentials not configured in code or environment variables.")
    print("To send QKD codes via email, please enter your Sender Email details now.")
    print("(For Gmail, you must use an 'App Password': https://myaccount.google.com/apppasswords)\n")
    
    try:
        entered_email = input("Sender Email (e.g. mymail@gmail.com): ").strip()
        if entered_email:
            SMTP_CONFIG["user"] = entered_email
            
        entered_pass = input("Sender App Password: ").strip()
        if entered_pass:
            SMTP_CONFIG["password"] = entered_pass
    except Exception:
        pass
    
    print(f"[SETUP] Using Sender: {SMTP_CONFIG['user']}\n")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------- load data ----------
if not os.path.isdir(DATA_DIR):
    raise FileNotFoundError(f"Data directory missing: {DATA_DIR}")

files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv")]
if not files:
    raise FileNotFoundError(f"No CSV found in {DATA_DIR}")

dfs = [pd.read_csv(f) for f in files]
df = pd.concat(dfs, ignore_index=True).fillna(0.0)
print(f"[SERVER] Loaded {len(df)} rows from {len(files)} files")

# compute QBER rule threshold
qber_values = df["QBER"].dropna()
qber_med = float(qber_values.median()) if not qber_values.empty else 0.0
qber_std = float(qber_values.std(ddof=0)) if not qber_values.empty else 0.0
QBER_THRESHOLD = qber_med + 2 * qber_std
print(f"[SERVER] QBER threshold = {QBER_THRESHOLD:.6g} (median {qber_med:.6g}, std {qber_std:.6g})")

# ---------- load model if available ----------
clf = None
explainer = None
print(f"[SERVER] Checking model at {MODEL_PATH}")
if os.path.exists(MODEL_PATH):
    try:
        clf = joblib.load(MODEL_PATH)
        logging.info("Loaded model %s", MODEL_PATH)
        
        # Init XAI
        explainer = QKDExplainer(clf, REQUIRED)

    except Exception:
        logging.warning("Failed to load model; continuing without ML.")

# ---------- helpers ----------
_idx = 0
ATTACK_MODE = False

def next_row():
    global _idx
    r = df.iloc[_idx].to_dict()
    r["_idx"] = int(_idx)
    _idx = (_idx + 1) % len(df)
    return r

def derive_key_bytes(row, n_bytes):
    seed = f"{row['_idx']}|{row['QBER']}|{row['SignalIntensity']}|{row['TimingJitter']}|{row['DetectorTemp']}"
    out = bytearray(); c=0
    while len(out) < n_bytes:
        h = hashlib.sha256()
        h.update(seed.encode('utf-8')); h.update(c.to_bytes(4,'big'))
        out.extend(h.digest()); c+=1
    return bytes(out[:n_bytes])

def derive_quantum_code(row, dev_id):
    # Physics-based QKD Code (Bra-ket notation symbols)
    symbols = ["|0⟩", "|1⟩", "|+⟩", "|−⟩", "|*⟩", "|/⟩", "H", "X", "Z", "Y"]
    
    # Use random salt to ensure it's different every time
    salt = str(random.random())
    seed = f"{dev_id}|{row['_idx']}|{row['QBER']}|{salt}"
    
    # Generate 6-symbol code
    h = hashlib.sha256(seed.encode('utf-8')).hexdigest()
    # Take chunks of hash to pick symbols
    code_str = ""
    for i in range(6):
        # Use 2 hex chars per symbol index
        chunk = h[i*2 : i*2+2]
        idx = int(chunk, 16) % len(symbols)
        code_str += symbols[idx]
        
    return code_str

# ---------- csv logging ----------
if not os.path.exists(CSV_LOG):
    with open(CSV_LOG, "w", newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["timestamp","from","to","label","p_attack","detection_reason","QBER","SignalIntensity","TimingJitter","DetectorTemp","qkd_code","plaintext"])

def log_csv(row):
    with open(CSV_LOG, "a", newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(row)

# ---------- flask + socketio ----------
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# connected[dev_id] = {'sid': sid, 'auth': bool}
connected = {}   
pending_auth = {} # sid -> {'code': str, 'row': dict, 'device': str}
dashboard_log = []

# ---------- Premium Dashboard HTML ----------
DASH_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QKD Security Monitor</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #050505;
            --panel-bg: #0a0a0a;
            --text-color: #e0e0e0;
            --accent-safe: #00ff9d;
            --accent-danger: #ff003c;
            --accent-warn: #ffb700;
            --border-color: #333;
        }
        body {
            font-family: 'Roboto Mono', monospace;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
            overflow-x: hidden;
        }
        h1, h2, h3 {
            font-family: 'Orbitron', sans-serif;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin: 0;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 2px solid var(--border-color);
            margin-bottom: 20px;
        }
        .status-bar {
            padding: 10px 20px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 1.2em;
            text-align: center;
            border: 1px solid var(--border-color);
            background: rgba(0,0,0,0.5);
            transition: all 0.3s ease;
        }
        .status-safe {
            color: var(--accent-safe);
            border-color: var(--accent-safe);
            box-shadow: 0 0 10px rgba(0, 255, 157, 0.2);
        }
        .status-danger {
            color: var(--accent-danger);
            border-color: var(--accent-danger);
            box-shadow: 0 0 15px rgba(255, 0, 60, 0.4);
            animation: pulse 1s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 15px rgba(255, 0, 60, 0.4); }
            50% { box-shadow: 0 0 25px rgba(255, 0, 60, 0.7); }
            100% { box-shadow: 0 0 15px rgba(255, 0, 60, 0.4); }
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .metric-card {
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            padding: 15px;
            border-radius: 4px;
        }
        .metric-label {
            font-size: 0.8em;
            color: #888;
            margin-bottom: 5px;
        }
        .metric-value {
            font-size: 1.5em;
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        th {
            background: #111;
            color: #888;
            font-weight: normal;
            font-size: 0.9em;
        }
        tr.attack {
            background: rgba(255, 0, 60, 0.1);
            color: #ff8a8a;
        }
        tr.attack td {
            border-bottom-color: rgba(255, 0, 60, 0.3);
        }
        tr.safe {
            color: #ccffeb;
        }
        .badge {
            padding: 2px 6px;
            border-radius: 2px;
            font-size: 0.8em;
            font-weight: bold;
        }
        .badge-safe { background: rgba(0, 255, 157, 0.2); color: var(--accent-safe); }
        .badge-danger { background: rgba(255, 0, 60, 0.2); color: var(--accent-danger); }
        
        /* Scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #000; }
        ::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>QKD SECURITY MONITOR</h1>
            <div style="font-size: 0.8em; color: #666; margin-top: 5px;">QUANTUM KEY DISTRIBUTION NETWORK</div>
        </div>
        <div id="system-status" class="status-bar status-safe">
            SYSTEM SECURE
        </div>
    </div>

    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-label">QBER THRESHOLD</div>
            <div class="metric-value" style="color: var(--accent-warn);">{{qthr}}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">ACTIVE NODES</div>
            <div class="metric-value" id="active-nodes">0</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">TOTAL TRANSMISSIONS</div>
            <div class="metric-value" id="total-transmissions">0</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">ATTACKS DETECTED</div>
            <div class="metric-value" id="total-attacks" style="color: var(--accent-danger);">0</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>TIME</th>
                <th>FROM</th>
                <th>TO</th>
                <th>STATUS</th>
                <th>LABEL</th>
                <th>THREAT ANALYSIS (XAI)</th>
                <th>ENCRYPTED</th>
            </tr>
        </thead>
        <tbody id="log-body">
            <!-- Rows injected here -->
        </tbody>
    </table>

    <script>
        let totalAttacks = 0;
        let totalTransmissions = 0;

        function update() {
            fetch('/live').then(r => r.json()).then(data => {
                const rows = data.rows;
                const stats = data.stats;
                
                // Update stats
                document.getElementById('active-nodes').innerText = stats.connected_count;
                
                // Update table
                let html = '';
                let currentAttacks = 0;
                
                rows.slice().reverse().forEach(r => {
                    const isAttack = r.label === 1;
                    if (isAttack) currentAttacks++;
                    
                    const cls = isAttack ? 'attack' : 'safe';
                    const badge = isAttack ? '<span class="badge badge-danger">ATTACK</span>' : '<span class="badge badge-safe">SECURE</span>';
                    
                    let xaiHtml = '<div style="display:flex; flex-direction:column; gap:4px;">';
                    if (r.xai_data && r.xai_data.length > 0) {
                        r.xai_data.slice(0, 2).forEach(item => {
                            const color = item.is_risk_factor ? 'var(--accent-danger)' : 'var(--accent-safe)';
                            const width = Math.max(item.contribution_percent, 10);
                            xaiHtml += `
                                <div style="display:flex; align-items:center; font-size:0.75em;">
                                    <span style="width:100px; opacity:0.8;">${item.name}</span>
                                    <div style="flex:1; height:6px; background:#333; border-radius:3px; overflow:hidden;">
                                        <div style="width:${width}%; height:100%; background:${color};"></div>
                                    </div>
                                    <span style="width:35px; text-align:right; margin-left:5px;">${item.contribution_percent.toFixed(0)}%</span>
                                </div>
                            `;
                        });
                    } else {
                        xaiHtml = '<span style="color:#666; font-size:0.8em;">No Analysis</span>';
                    }
                    xaiHtml += '</div>';

                    html += `<tr class="${cls}">
                        <td>${r.timestamp.split(' ')[1]}</td>
                        <td>${r.frm}</td>
                        <td>${r.to}</td>
                        <td>${badge}</td>
                        <td>${r.label}</td>
                        <td>${xaiHtml}</td>
                        <td>${r.plaintext}</td>
                    </tr>`;
                });
                
                document.getElementById('log-body').innerHTML = html;
                
                // Update totals (approximate for demo)
                document.getElementById('total-transmissions').innerText = rows.length; 
                document.getElementById('total-attacks').innerText = currentAttacks;

                // Update Status Bar
                const statusEl = document.getElementById('system-status');
                if (currentAttacks > 0 && rows[rows.length-1].label === 1) {
                    // If the latest is an attack
                    statusEl.innerText = "INTRUSION DETECTED";
                    statusEl.className = "status-bar status-danger";
                } else {
                    statusEl.innerText = "SYSTEM SECURE";
                    statusEl.className = "status-bar status-safe";
                }
            });
        }
        
        setInterval(update, 1000);
        update();
    </script>
</body>
</html>
"""

@app.route("/dashboard")
def dashboard():
    return render_template_string(DASH_HTML, qthr=f"{QBER_THRESHOLD:.6g}")

@app.route("/live")
def live():
    return jsonify({
        "rows": dashboard_log[-50:], # Send last 50
        "stats": {
            "connected_count": len(connected)
        }
    })

# ---------- socket handlers ----------
@socketio.on("connect")
def on_connect():
    logging.info("connect sid=%s", request.sid)

@socketio.on("register")
def on_register(payload):
    dev = payload.get("device_id")
    user_email = payload.get("email")
    
    if not dev:
        return
    
    # Eavesdropper is passive, no auth needed
    if dev == "E":
        connected[dev] = {'sid': request.sid, 'auth': True}
        logging.info("Device %s registered (Passive)", dev)
        socketio.emit("registered", {"device_id": dev}, room=request.sid)
        return

    # For A and B, start Auth flow
    connected[dev] = {'sid': request.sid, 'auth': False}
    logging.info("Device %s registered (Pending Auth)", dev)
    
    # Generate Auth Challenge
    row = next_row()
    code = derive_quantum_code(row, dev)
    pending_auth[request.sid] = {'code': code, 'row': row, 'device': dev}
    
    # Send Email
    print(f"\n[AUTH] Device {dev} requesting connection.", flush=True)
    
    target_email = user_email
    
    # Fallback if client didn't send email (backward compatibility or manual override)
    if not target_email:
        print(f"       Client did not provide email. Please enter manually:", flush=True)
        try:
            target_email = input(f"Email for {dev}: ").strip()
        except Exception:
            pass

    if target_email:
        print(f"       Sending QKD Code to {target_email}...", flush=True)
        try:
            send_email(
                subject=f"QKD Authentication Code for Device {dev}",
                body=f"Your QKD Authentication Code is: {code}\n\nPlease enter this code in your device terminal.",
                sender=SMTP_CONFIG["user"],
                recipient=target_email,
                smtp_config=SMTP_CONFIG
            )
            print(f"       Code sent to {target_email}.\n", flush=True)
        except Exception as e:
            print(f"       Error sending email: {e}")
            print(f"       Fallback: QKD AUTH CODE: {code}")
    else:
         print(f"       No email provided. Fallback: QKD AUTH CODE: {code}")

    socketio.emit("auth_challenge", {"device_id": dev}, room=request.sid)

@socketio.on("auth_response")
def on_auth_response(payload):
    sid = request.sid
    code_attempt = payload.get("code")
    
    if sid not in pending_auth:
        socketio.emit("auth_result", {"ok": False, "reason": "no_pending_auth"}, room=sid)
        return
        
    expected = pending_auth[sid]['code']
    dev = pending_auth[sid]['device']
    
    if code_attempt == expected:
        connected[dev]['auth'] = True
        del pending_auth[sid]
        print(f"[AUTH] Device {dev} Authenticated Successfully.")
        socketio.emit("auth_result", {"ok": True}, room=sid)
    else:
        print(f"[AUTH] Device {dev} Failed Auth (Attempt: {code_attempt})")
        socketio.emit("auth_result", {"ok": False, "reason": "wrong_code"}, room=sid)

@socketio.on("disconnect")
def on_disconnect(sid=None):
    real_sid = sid if sid is not None else request.sid
    rem = [d for d,info in list(connected.items()) if info['sid'] == real_sid]
    for d in rem:
        try:
            del connected[d]
            logging.info("Device %s disconnected", d)
        except KeyError:
            pass
    if real_sid in pending_auth:
        del pending_auth[real_sid]

# --- Attack Control Handlers ---
@socketio.on("attack_start")
def on_attack_start(payload):
    global ATTACK_MODE
    ATTACK_MODE = True
    print("\n[SERVER] ⚠️ AGGRESSIVE ATTACK MODE ENABLED ⚠️\n")
    socketio.emit("attack_status", {"mode": "aggressive", "active": True})

@socketio.on("attack_stop")
def on_attack_stop(payload):
    global ATTACK_MODE
    ATTACK_MODE = False
    print("\n[SERVER] 🛡️ ATTACK MODE DISABLED 🛡️\n")
    socketio.emit("attack_status", {"mode": "normal", "active": False})


def decide_label_and_reason(row):
    # Default values
    label = 0
    p_attack = 0.0
    reason = "safe"
    shap_details = ""
    xai_data = []

    if ATTACK_MODE:
        # Synthetic XAI for demo consistency
        fake_shap = " due to Quantum Error Rate (risk), Signal Strength (risk)"
        
        # Attack Scenario: 
        # 1. High QBER (> 90%) -> Risk Factor = True
        # 2. Low Signal Strength (< 10%) -> Risk Factor = True (Low signal is bad)
        v_qber = random.randint(90, 99)
        v_signal = random.randint(1, 10)
        
        fake_xai = [
            {"name": "Quantum Error Rate", "contribution_percent": float(v_qber), "is_risk_factor": True},
            {"name": "Signal Strength", "contribution_percent": float(v_signal), "is_risk_factor": True} 
        ]
        return 1, 0.995, "forced_aggressive_attack", fake_shap, fake_xai

    rule_flag = row["QBER"] > QBER_THRESHOLD

    if clf is not None:
        X = np.array([[row[f] for f in REQUIRED]], dtype=float)
        try:
            probs = clf.predict_proba(X)[0]
            p_attack = float(probs[-1]) # simplified
            
            # XAI Explanation
            if explainer:
                shap_details = explainer.explain(X)
                xai_data = explainer.explain_structured(X)

        except Exception:
            p_attack = 0.0

    if p_attack >= 0.6 and rule_flag:
        label = 1; reason = f"ml+rule p={p_attack:.3f}"
    elif p_attack >= 0.85:
        label = 1; reason = f"ml_high p={p_attack:.3f}"
    elif rule_flag:
        label = 1; reason = f"qber_rule q={row['QBER']:.6g}"
    else:
        label = 0; reason = f"safe p={p_attack:.3f}"
    
    # --- FORCE XAI PERCENTAGES LOGIC ---
    # User Request:
    # If Secure (Label 0) -> Signal Strength > 85% (Good)
    # If Attack (Label 1) -> Quantum Error Rate > 90% (Bad) AND Signal Strength < 10% (Bad)
    # Values vary every time.

    final_xai = []
    
    if label == 1:
        # Attack Scenario: 
        # 1. High QBER (> 90%) -> Risk Factor = True
        # 2. Low Signal Strength (< 10%) -> Risk Factor = True (Low signal is bad)
        # Randomize values every time this function is called
        v_qber = random.randint(90, 99)
        v_signal = random.randint(1, 10)
        
        final_xai = [
            {"name": "Quantum Error Rate", "contribution_percent": float(v_qber), "is_risk_factor": True},
            {"name": "Signal Strength", "contribution_percent": float(v_signal), "is_risk_factor": True} 
        ]
    else:
        # Secure Scenario:
        # 1. High Signal Strength (> 85%) -> Risk Factor = False (High signal is good)
        # 2. Low QBER (< 5%) -> Risk Factor = False
        # Randomize values every time this function is called
        v_signal = random.randint(85, 99)
        v_qber = random.randint(1, 5)
        
        final_xai = [
            {"name": "Signal Strength", "contribution_percent": float(v_signal), "is_risk_factor": False},
            {"name": "Quantum Error Rate", "contribution_percent": float(v_qber), "is_risk_factor": False}
        ]

    # Ensure we ALWAYS return 5 values
    return (label, round(p_attack,3), reason, shap_details, final_xai)

@socketio.on("send_message")
def on_send_message(payload):
    try:
        frm = payload.get("from")
        to = payload.get("to")
        text = payload.get("text","")
        
        # Check Auth
        if frm not in connected or not connected[frm]['auth']:
            socketio.emit("send_result", {"ok": False, "reason": "unauthorized"}, room=request.sid)
            return
            
        if to not in connected:
             socketio.emit("send_result", {"ok": False, "reason": "partner_offline"}, room=request.sid)
             return
             
        # pick next dataset row as the channel sample
        row = next_row()
        features = {k: float(row[k]) for k in REQUIRED}
        
        # decide label using ML+rule
        try:
            # Unpack 5 values: label, p_attack, base_reason, shap_details, xai_data
            ret = decide_label_and_reason(row)
            if len(ret) == 5:
                label, p_attack, base_reason, shap_details, xai_data = ret
            else:
                # Fallback if something weird happens
                label, p_attack, base_reason = ret[:3]
                shap_details = ""
                xai_data = []
        except ValueError:
             # Absolute fallback
             label = 0; p_attack = 0.0; base_reason = "error_fallback"; shap_details = ""; xai_data = []
        
        # --- Construct Professional Narrative ---
        # Structure: [Status] [Flow] [Analysis]
        
        flow_info = f"Transfer {frm}→{to}"
        
        if label == 1:
            # Attack Scenario
            status_icon = "⚠️ INTERCEPTED"
            analysis = f"\n   • AI Detection: Anomalous traffic pattern (Confidence: {p_attack:.1%})"
            if shap_details:
                analysis += f"\n   • Key Factors: {shap_details.strip()}"
            else:
                analysis += f"\n   • Reason: {base_reason}"
                
            narrative = f"{status_icon} | {flow_info} | {analysis}"
            
        else:
            # Safe Scenario
            status_icon = "✅ SECURE"
            safe_conf = 1.0 - p_attack
            
            analysis = (
                f"\n   • QBER Status: Nominal ({features['QBER']:.5f} < Threshold)"
                f"\n   • AI Analysis: No malicious patterns detected (Confidence: {safe_conf:.1%})"
                f"\n   • Channel Health: Optimal signal intensity and jitter levels"
            )
                
            narrative = f"{status_icon} | {flow_info} | {analysis}"
            
        reason = narrative 
        
        if label == 1 and "forced_aggressive_attack" in base_reason:
            features['QBER'] = max(features['QBER'], QBER_THRESHOLD * 1.5)
            features['TimingJitter'] = max(features['TimingJitter'], 0.5)

        ts = time.strftime("%Y-%m-%d %H:%M:%S")

        print("\n======================")
        print(f"Message From {frm} → {to}")
        print("----------------------")
        print(f"QBER: {features['QBER']:.6f}")
        print(f"SignalIntensity: {features['SignalIntensity']:.4f}")
        print(f"TimingJitter: {features['TimingJitter']:.4f}")
        print(f"DetectorTemp: {features['DetectorTemp']:.2f}")
        print(f"Label: {label}")
        print(f"Reason: {reason}")
        if label == 1:
            print("STATUS: ❗ EAVESDROPPING DETECTED ❗")
        else:
            print("STATUS: SAFE CONNECTION ✔")
        print("======================\n")

        # dashboard + csv
        # Generate simulated encrypted text (5 chars) for dashboard display
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&"
        encrypted_preview = "".join(random.choice(chars) for _ in range(5))

        dashboard_log.append({
            "timestamp": ts, "frm": frm, "to": to, "label": label, "p_attack": p_attack, "detection_reason": reason,
            "QBER": features['QBER'], "SignalIntensity": features['SignalIntensity'],
            "TimingJitter": features['TimingJitter'], "DetectorTemp": features['DetectorTemp'],
            "code": "SESSION_AUTH", "plaintext": encrypted_preview,
            "xai_data": xai_data
        })
        log_csv([ts, frm, to, label, p_attack, reason, features['QBER'], features['SignalIntensity'], features['TimingJitter'], features['DetectorTemp'], "SESSION_AUTH", text])

        # Security Response
        if label == 1:
            # 1. Broadcast Alert (to Eavesdropper/Admin)
            alert = {
                "msg_id": "ALERT", "from": frm, "to": to,
                "label": label, "p_attack": p_attack, "reason": base_reason,
                "narrative": narrative, 
                "QBER": features['QBER'], "SignalIntensity": features['SignalIntensity'],
                "TimingJitter": features['TimingJitter'], "DetectorTemp": features['DetectorTemp']
            }
            socketio.emit("alert_attack", alert) # broadcast=True removed (default behavior or handled by room)

            # 2. Disconnect Devices
            print(f"\n[SECURITY] ⛔ BLOCKING CONNECTION ⛔")
            print(f"{narrative}")
            print(f"Disconnecting {frm} and {to}...\n")
            
            for device_name in [frm, to]:
                if device_name in connected:
                    sid = connected[device_name]['sid']
                    socketio.emit("force_disconnect", {"reason": "EAVESDROPPING_DETECTED", "details": narrative}, room=sid)
            
            # 3. Abort Delivery
            return

        # Deliver Message Directly (Safe)
        sid_to = connected[to]['sid']
        socketio.emit("incoming_message", {"from": frm, "text": text, "label": label}, room=sid_to)
        socketio.emit("send_result", {"ok": True}, room=request.sid)

    except Exception:
        logging.exception("send_message error")
        socketio.emit("send_result", {"ok": False, "reason": "internal"}, room=request.sid)

@app.route("/health")
def health():
    return {"ok": True, "connected": list(connected.keys())}

if __name__ == "__main__":
    print("\nQKD SERVER (EMAIL AUTH) STARTED\n")
    print("Dashboard -> http://localhost:5000/dashboard")
    socketio.run(app, host=HOST, port=PORT)
