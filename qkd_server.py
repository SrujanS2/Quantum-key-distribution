"""
QKD SERVER with Dashboard + CSV logging
- Auto-loads CSVs from ./data
- Uses saved model if present (but for this flow we force label=0)
- Prints features for each message and shows SAFE status
- Issues 6-digit QKD code per pair
- Stores pending (locked) messages until receiver unlocks with code
"""

import os
import time
import random
import hashlib
import csv
import logging
import joblib
import numpy as np
import pandas as pd
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO
from crypto_utils import bytes_to_bits, otp_encrypt

# config
HOST = "0.0.0.0"
PORT = 5000
DATA_DIR = "data"
CSV_LOG = "qkd_logs.csv"
REQUIRED = ["QBER", "SignalIntensity", "TimingJitter", "DetectorTemp"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ----------------- load datasets (auto-detect) -----------------
files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv")] if os.path.isdir(DATA_DIR) else []
if not files:
    raise FileNotFoundError(f"No CSV datasets found in folder '{DATA_DIR}'. Place your CSVs there.")
dfs = [pd.read_csv(f) for f in files]
df = pd.concat(dfs, ignore_index=True).fillna(0.0)
print(f"[SERVER] Loaded {len(df)} rows from {len(files)} CSV(s)")

# optional: try to load model (not required for forced-safe flow)
MODEL_PATH = "qkd_rf_model.joblib"
clf = None
if os.path.exists(MODEL_PATH):
    try:
        clf = joblib.load(MODEL_PATH)
        logging.info("Loaded model %s", MODEL_PATH)
    except Exception:
        logging.warning("Failed to load model artifact; continuing without it")

# iterator over dataset rows
_idx = 0
def next_row():
    global _idx
    r = df.iloc[_idx].to_dict()
    r["_idx"] = int(_idx)
    _idx = (_idx + 1) % len(df)
    return r

# ----------------- helpers for key and qkd code -----------------
def derive_key_bytes(row, n_bytes):
    seed = f"{row['_idx']}|{row['QBER']}|{row['SignalIntensity']}|{row['TimingJitter']}|{row['DetectorTemp']}"
    out = bytearray()
    c = 0
    while len(out) < n_bytes:
        h = hashlib.sha256()
        h.update(seed.encode('utf-8'))
        h.update(c.to_bytes(4, 'big'))
        out.extend(h.digest())
        c += 1
    return bytes(out[:n_bytes])

def derive_6digit(row, pair_id):
    seed = f"{pair_id}|{row['_idx']}|{row['QBER']}"
    h = hashlib.sha256(seed.encode('utf-8')).hexdigest()
    code = int(h[:12],16) % 1000000
    return f"{code:06d}"

# ----------------- CSV logging initialization -----------------
if not os.path.exists(CSV_LOG):
    with open(CSV_LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp","from","to","label","confidence","QBER","SignalIntensity","TimingJitter","DetectorTemp","qkd_code","plaintext"])

def log_to_csv(row):
    with open(CSV_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(row)

# ----------------- flask + socketio -----------------
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

connected = {}  # device -> sid
pending = {}    # msg_id -> pending info
pair_codes = {}  # pair -> code
dashboard_log = []

# simple dashboard HTML
DASHBOARD_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>QKD Dashboard</title>
  <style>
    body{font-family:Arial;background:#0b0b0b;color:#eaeaea;padding:12px}
    table{width:100%;border-collapse:collapse}
    th,td{padding:8px;border:1px solid #333;text-align:center}
    tr.safe{background:#092009}
    tr.attack{background:#2b0b0b}
  </style>
  <script>
    setInterval(()=>fetch('/live').then(r=>r.json()).then(rows=>{
      let html='';
      rows.forEach(r=>{
        let cls = r.label==0 ? 'safe' : 'attack';
        html += `<tr class="${cls}"><td>${r.timestamp}</td><td>${r.frm}</td><td>${r.to}</td><td>${r.label}</td><td>${r.confidence}</td><td>${r.QBER}</td><td>${r.SignalIntensity}</td><td>${r.TimingJitter}</td><td>${r.DetectorTemp}</td><td>${r.code}</td><td>${r.plaintext}</td></tr>`;
      });
      document.getElementById('tbody').innerHTML = html;
    }), 1000);
  </script>
</head>
<body>
  <h1>QKD Dashboard</h1>
  <table>
    <thead><tr><th>Time</th><th>From</th><th>To</th><th>Label</th><th>Conf</th><th>QBER</th><th>Signal</th><th>Jitter</th><th>Temp</th><th>Code</th><th>Message</th></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
</body>
</html>
"""

@app.route("/dashboard")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/live")
def live():
    # return last 50 rows
    return jsonify(dashboard_log[-50:])

# ----------------- socket handlers -----------------
@socketio.on("connect")
def on_connect():
    logging.info("[connect] sid=%s", request.sid)

@socketio.on("register")
def on_register(payload):
    dev = payload.get("device_id")
    if not dev:
        return
    connected[dev] = request.sid
    logging.info("Device %s registered (sid=%s)", dev, request.sid)
    socketio.emit("registered", {"device_id": dev, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, room=request.sid)

@socketio.on("disconnect")
def on_disconnect(sid=None):
    real_sid = sid if sid is not None else request.sid
    rem = [d for d,s in list(connected.items()) if s == real_sid]
    for d in rem:
        try:
            del connected[d]
            logging.info("Device %s disconnected (sid=%s)", d, real_sid)
        except KeyError:
            pass

@socketio.on("send_message")
def on_send_message(payload):
    try:
        frm = payload.get("from")
        to = payload.get("to")
        text = payload.get("text","")
        if not frm or not to or text == "":
            socketio.emit("send_result", {"ok": False, "reason": "missing_fields"}, room=request.sid)
            return

        row = next_row()
        features = {k: float(row[k]) for k in REQUIRED}

        # FORCE SAFE LABEL per your requirement
        label = 0
        confidence = 1.0

        pair = f"{frm}->{to}"
        # generate/reset code each message
        code = derive_6digit(row, pair)
        pair_codes[pair] = code

        msg_id = f"m_{int(time.time()*1000)}_{random.randint(0,9999)}"
        ts = time.strftime("%Y-%m-%d %H:%M:%S")

        # OTP encrypt
        msg_bytes = text.encode('utf-8')
        kb = derive_key_bytes(row, len(msg_bytes))
        kbits = bytes_to_bits(kb)
        try:
            ct = otp_encrypt(msg_bytes, kbits)
            ct_hex = ct.hex()
        except Exception:
            ct_hex = ""

        # store pending
        pending[msg_id] = {"msg_id":msg_id,"timestamp":ts,"from":frm,"to":to,"cipher_hex":ct_hex,"row":row,"qkd_code":code,"plaintext":text}

        # server console print (features + label)
        print("\n======================")
        print(f"Message From {frm} → {to}")
        print("----------------------")
        print(f"QBER:              {features['QBER']}")
        print(f"SignalIntensity:   {features['SignalIntensity']}")
        print(f"TimingJitter:      {features['TimingJitter']}")
        print(f"DetectorTemp:      {features['DetectorTemp']}")
        print(f"Label:             {label}   (confidence={confidence:.3f})")
        print("STATUS: SAFE CONNECTION ✔")
        print(f"Generated QKD Code: {code}")
        print("======================\n")

        # dashboard + csv log
        dashboard_log.append({
            "timestamp": ts, "frm": frm, "to": to, "label": label, "confidence": round(confidence,3),
            "QBER": features['QBER'], "SignalIntensity": features['SignalIntensity'],
            "TimingJitter": features['TimingJitter'], "DetectorTemp": features['DetectorTemp'],
            "code": code, "plaintext": text
        })

        log_to_csv([ts, frm, to, label, confidence, features['QBER'], features['SignalIntensity'], features['TimingJitter'], features['DetectorTemp'], code, text])

        # notify receiver: send only locked alert (no plaintext)
        sid_to = connected.get(to)
        if sid_to:
            socketio.emit("incoming_locked", {"msg_id": msg_id, "from": frm}, room=sid_to)

        # confirm to sender that message is queued
        socketio.emit("send_result", {"ok": True, "msg_id": msg_id, "status": "pending"}, room=request.sid)

    except Exception:
        logging.exception("send_message error")
        socketio.emit("send_result", {"ok": False, "reason": "internal"}, room=request.sid)

@socketio.on("unlock_attempt")
def on_unlock_attempt(payload):
    try:
        device = payload.get("device")
        msg_id = payload.get("msg_id")
        code = payload.get("code")
        if not device or not msg_id or not code:
            socketio.emit("unlock_failed", {"msg_id": msg_id, "reason": "missing_fields"}, room=request.sid); return
        pend = pending.get(msg_id)
        if not pend:
            socketio.emit("unlock_failed", {"msg_id": msg_id, "reason": "not_found"}, room=request.sid); return
        p = f"{pend['from']}->{pend['to']}"
        expected = pend.get("qkd_code")
        if expected != code:
            socketio.emit("unlock_failed", {"msg_id": msg_id, "reason": "wrong_code"}, room=request.sid); return

        # decrypt and deliver
        ct = bytes.fromhex(pend["cipher_hex"]) if pend["cipher_hex"] else b""
        if ct:
            row = pend["row"]
            kb = derive_key_bytes(row, len(ct))
            kbits = bytes_to_bits(kb)
            try:
                key_bytes = bytes_to_bits(kb)  # bytes_to_bits returns list, but use otp_decrypt? simpler de-xor:
                # perform decryption using same method used earlier
                # reconstruct key bytes and XOR
                key_bytes_b = derive_key_bytes(row, len(ct))
                pt = bytes([c ^ k for c,k in zip(ct, key_bytes_b)]).decode('utf-8', errors='replace')
            except Exception:
                pt = "<decryption_failed>"
        else:
            pt = pend["plaintext"]

        sid_dev = connected.get(device)
        if sid_dev:
            socketio.emit("incoming_decrypted", {"msg_id": msg_id, "from": pend["from"], "plaintext": pt}, room=sid_dev)
        sid_fr = connected.get(pend["from"])
        if sid_fr:
            socketio.emit("message_status", {"msg_id": msg_id, "status":"delivered"}, room=sid_fr)

        # log delivered
        log_to_csv([time.strftime("%Y-%m-%d %H:%M:%S"), pend["from"], pend["to"], 0, 1.0, pend["row"]["QBER"], pend["row"]["SignalIntensity"], pend["row"]["TimingJitter"], pend["row"]["DetectorTemp"], pend["qkd_code"], pt])

        del pending[msg_id]

    except Exception:
        logging.exception("unlock error")
        socketio.emit("unlock_failed", {"msg_id": payload.get("msg_id"), "reason":"internal"}, room=request.sid)

@app.route("/health")
def health():
    return {"ok": True, "pending": len(pending), "connected": list(connected.keys())}

if __name__ == "__main__":
    print("\nQKD SERVER STARTED\n")
    print("Dashboard -> http://localhost:5000/dashboard")
    socketio.run(app, host=HOST, port=PORT)
