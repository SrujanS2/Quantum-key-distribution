# qkd_server_dataset_mode.py
"""
QKD server (dataset-driven mode).
- On each incoming send_message, the server reads the next unused row
  from the dataset (in-memory pointer) and uses its four features for scoring.
- Key material: deterministic stream derived from the row values (SHA256 chain).
- Emits incoming_encrypted and incoming_decrypted events (demo).
- Lazy model loading: tries to load qkd_rf_model.joblib if present.
"""

import os, time, random, logging, threading, hashlib, json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit, join_room

import numpy as np
import pandas as pd

# crypto helpers (simple OTP using bits -> bytes)
def bytes_to_bits(b: bytes):
    bits = []
    for byte in b:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits

def bits_to_bytes(bits):
    if len(bits) % 8 != 0:
        raise ValueError("bits length must be multiple of 8")
    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for b in bits[i:i+8]:
            byte = (byte << 1) | (int(b) & 1)
        out.append(byte)
    return bytes(out)

def otp_encrypt(msg_bytes: bytes, key_bits):
    # key_bits is list of 0/1 at least len(msg_bytes)*8
    if len(key_bits) < len(msg_bytes)*8:
        raise ValueError("Not enough key bits")
    key_bytes = bits_to_bytes(key_bits[:len(msg_bytes)*8])
    ct = bytes([mb ^ kb for mb, kb in zip(msg_bytes, key_bytes)])
    return ct

def otp_decrypt(ct_bytes: bytes, key_bits):
    # symmetric
    return otp_encrypt(ct_bytes, key_bits)

# ---- dataset-driven server ----
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "key.csv"
MODEL_PATH = Path("qkd_rf_model.joblib")
LOG_CSV = DATA_DIR / "device_chat_dataset_mode.csv"

HOST = "0.0.0.0"
PORT = int(os.getenv("QKD_SERVER_PORT", "5000"))
FORCE_DELIVER = os.getenv("FORCE_DELIVER", "0").lower() in ("1","true","yes")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

connected_devices: Dict[str, str] = {}

# load dataset into memory
if not CSV_PATH.exists():
    raise FileNotFoundError(f"Dataset not found at {CSV_PATH}")
_df = pd.read_csv(CSV_PATH)
# ensure expected features
FEATURES = ["QBER", "SignalIntensity", "TimingJitter", "DetectorTemp"]
for f in FEATURES:
    if f not in _df.columns:
        raise ValueError(f"CSV missing expected feature column: {f}")
_df = _df.reset_index(drop=True)
_dataset_lock = threading.Lock()
_dataset_idx = 0  # global pointer into dataset

def get_next_row():
    global _dataset_idx
    with _dataset_lock:
        if _dataset_idx >= len(_df):
            # loop around if exhausted (or raise)
            _dataset_idx = 0
        row = _df.iloc[_dataset_idx]
        _dataset_idx += 1
    return row.to_dict()

# lazy model load
MODEL_LOADED = False
model = None
scaler = None
model_features = None
try:
    import joblib
    if MODEL_PATH.exists():
        art = joblib.load(MODEL_PATH)
        model = art.get("model")
        scaler = art.get("scaler")
        model_features = art.get("features")
        MODEL_LOADED = (model is not None and scaler is not None and model_features is not None)
        logging.info("Model loaded? %s, features:%s", MODEL_LOADED, model_features)
    else:
        logging.info("No model file found at %s. Server will run but scoring disabled.", MODEL_PATH)
except Exception:
    logging.exception("Model load failed; scoring disabled")

def score_features(feat_dict):
    if not MODEL_LOADED:
        return None, 0, None
    # order features as model expects
    X = np.array([float(feat_dict.get(f, 0.0)) for f in model_features]).reshape(1,-1)
    try:
        Xs = scaler.transform(X)
    except Exception:
        Xs = X
    try:
        probs = model.predict_proba(Xs)
        prob = float(probs[0,1]) if probs.ndim>1 and probs.shape[1]>1 else float(probs[0])
        label = int(prob >= 0.5)
        return prob, label, None
    except Exception:
        logging.exception("Scoring failed")
        return None, 0, None

# Deterministic key derivation from feature row:
# we serialize feature values and feed into a SHA256 counter hash chain to produce as many bytes as needed.
def derive_key_bytes_from_row(row: dict, n_bytes: int) -> bytes:
    seed = "|".join(f"{k}={row.get(k,'')}" for k in FEATURES)
    out = bytearray()
    counter = 0
    while len(out) < n_bytes:
        h = hashlib.sha256()
        h.update(seed.encode("utf-8"))
        h.update(counter.to_bytes(4, "big"))
        digest = h.digest()
        out.extend(digest)
        counter += 1
    return bytes(out[:n_bytes])

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def persist_row(r):
    cols = ["msg_id","timestamp_sent","from_device","to_device","plaintext","cipher_hex","encryption_mode","pred_prob","pred_label","status","timestamp_delivered"] + FEATURES
    write_hdr = not LOG_CSV.exists()
    df = pd.DataFrame([r])
    df = df.reindex(columns=cols)
    df.to_csv(LOG_CSV, mode="a", header=write_hdr, index=False)

# socket handlers
@socketio.on("register")
def on_register(payload):
    device = payload.get("device_id")
    if not device:
        emit("error", {"msg":"missing device_id"})
        return
    connected_devices[device] = request.sid
    join_room(device)
    logging.info("Device %s connected sid=%s", device, request.sid)
    emit("registered", {"device_id": device, "time": utc_now_iso()})

@socketio.on("disconnect")
def on_disconnect(*args):
    try:
        sid = request.sid
    except Exception:
        return
    to_remove = [d for d,s in connected_devices.items() if s == sid]
    for d in to_remove:
        del connected_devices[d]
        logging.info("Device %s disconnected", d)

@socketio.on("send_message")
def on_send_message(payload):
    try:
        frm = payload.get("from")
        to = payload.get("to")
        text = payload.get("text", "")
        if not frm or not to or text == "":
            emit("send_result", {"ok":False, "reason":"missing fields"})
            return

        # get next dataset row and use its features
        row = get_next_row()  # dictionary of all columns; we will read FEATURES from it
        features = {k: float(row.get(k, 0.0)) for k in FEATURES}
        pred_prob, pred_label, _ = score_features(features)
        logging.info("Using dataset row idx=%s features=%s => prob=%s label=%s", _dataset_idx-1, features, pred_prob, pred_label)

        # derive deterministic key bytes from this row
        msg_bytes = text.encode("utf-8")
        nbytes = len(msg_bytes)
        key_bytes = derive_key_bytes_from_row(row, nbytes)
        key_bits = bytes_to_bits(key_bytes)

        # OTP encrypt
        ct = otp_encrypt(msg_bytes, key_bits)
        cipher_hex = ct.hex()
        enc_mode = "OTP-derived-from-row"

        # persist pending
        sent_ts = utc_now_iso()
        msg_id = f"msg_{int(time.time()*1000)}_{random.randint(0,9999)}"
        persist_row({
            "msg_id": msg_id,
            "timestamp_sent": sent_ts,
            "from_device": frm,
            "to_device": to,
            "plaintext": "<cipher pending>",
            "cipher_hex": cipher_hex,
            "encryption_mode": enc_mode,
            "pred_prob": pred_prob,
            "pred_label": pred_label,
            "status": "pending",
            **{k: features[k] for k in FEATURES}
        })

        # background deliver
        def deliver():
            time.sleep(0.3)
            # drop if attack and not forced
            force_flag = bool(payload.get("force_deliver", False))
            if (pred_label != 0) and (not FORCE_DELIVER) and (not force_flag):
                logging.info("Dropping msg %s due to pred_label=%s", msg_id, pred_label)
                persist_row({
                    "msg_id": msg_id,
                    "timestamp_sent": sent_ts,
                    "from_device": frm,
                    "to_device": to,
                    "plaintext": "<dropped>",
                    "cipher_hex": cipher_hex,
                    "encryption_mode": enc_mode,
                    "pred_prob": pred_prob,
                    "pred_label": pred_label,
                    "status": "dropped",
                    **{k: features[k] for k in FEATURES}
                })
                sid_sender = connected_devices.get(frm)
                if sid_sender:
                    socketio.emit("message_status", {"msg_id": msg_id, "status":"dropped","pred_prob":pred_prob}, room=sid_sender)
                return

            # decrypt (server-side demo using same derived key)
            try:
                recovered = otp_decrypt(ct, key_bits).decode("utf-8", errors="replace")
            except Exception:
                recovered = "<decryption_failed>"

            persist_row({
                "msg_id": msg_id,
                "timestamp_sent": sent_ts,
                "from_device": frm,
                "to_device": to,
                "plaintext": recovered,
                "cipher_hex": cipher_hex,
                "encryption_mode": enc_mode,
                "pred_prob": pred_prob,
                "pred_label": pred_label,
                "status": "delivered",
                "timestamp_delivered": utc_now_iso(),
                **{k: features[k] for k in FEATURES}
            })

            # send encrypted metadata then decrypted to recipient
            sid_rec = connected_devices.get(to)
            if sid_rec:
                socketio.emit("incoming_encrypted", {"msg_id": msg_id, "from": frm, "cipher_hex": cipher_hex, "encryption_mode": enc_mode, "pred_prob": pred_prob}, room=sid_rec)
                socketio.emit("incoming_decrypted", {"msg_id": msg_id, "from": frm, "plaintext": recovered, "pred_prob": pred_prob}, room=sid_rec)

            sid_sender = connected_devices.get(frm)
            if sid_sender:
                socketio.emit("message_status", {"msg_id": msg_id, "status":"delivered","pred_prob":pred_prob}, room=sid_sender)

        socketio.start_background_task(deliver)
        emit("send_result", {"ok":True, "msg_id": msg_id, "pred_prob": pred_prob, "pred_label": pred_label, "encryption_mode": enc_mode})
    except Exception:
        logging.exception("send_message failed")
        emit("send_result", {"ok":False, "reason":"internal_error"})

@app.route("/health")
def health():
    return jsonify({"ok":True,"time":utc_now_iso(),"model_loaded": MODEL_LOADED, "dataset_rows": len(_df)})

@app.route("/admin/reset_index", methods=["POST"])
def admin_reset():
    global _dataset_idx
    _dataset_idx = 0
    return jsonify({"ok":True,"idx":_dataset_idx})

if __name__ == "__main__":
    logging.info("Starting dataset-driven QKD server on %s:%s", HOST, PORT)
    socketio.run(app, host=HOST, port=PORT)
