"""
device_client.py - updated to show immediate popup on alert_attack

Usage:
  python device_client.py --server http://localhost:5000 --device A
"""

import argparse
import socketio
import os
import sys
import time
import threading

# tkinter for popup
try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None
    messagebox = None

# optional Windows beep
try:
    import winsound
except Exception:
    winsound = None

parser = argparse.ArgumentParser()
parser.add_argument("--server", required=True)
parser.add_argument("--device", required=True)
args = parser.parse_args()

SERVER = args.server.rstrip("/")
DEVICE = args.device.upper()

sio = socketio.Client()
attempts = {}  # msg_id -> count

def clear():
    os.system("cls" if os.name == "nt" else "clear")

# ---------- UI helper: popup in separate thread ----------
def show_alert_popup(data):
    """
    Show a GUI popup with alert details. Runs in a daemon thread.
    """
    title = "EAVESDROP ALERT"
    lines = []
    # build friendly message from data dict
    if isinstance(data, dict):
        frm = data.get("from", "")
        to = data.get("to", "")
        p_attack = data.get("p_attack", data.get("p_attack", ""))
        reason = data.get("reason", data.get("detection_reason", ""))
        qber = data.get("QBER", "")
        jitter = data.get("TimingJitter", "")
        sig = data.get("SignalIntensity", "")
        temp = data.get("DetectorTemp", "")
        lines.append(f"From: {frm}  →  To: {to}")
        lines.append(f"Reason: {reason}")
        lines.append(f"p_attack: {p_attack}")
        lines.append(f"QBER: {qber}  Signal: {sig}  Jitter: {jitter}  Temp: {temp}")
    else:
        lines.append(str(data))
    text = "\n".join(lines)

    # beep
    try:
        if winsound:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        else:
            # fallback terminal bell
            sys.stdout.write("\a"); sys.stdout.flush()
    except Exception:
        pass

    # try tkinter popup if available
    if tk and messagebox:
        try:
            root = tk.Tk()
            root.withdraw()
            # ensure the popup is on top
            root.attributes("-topmost", True)
            messagebox.showwarning(title, text, parent=root)
            try:
                root.destroy()
            except Exception:
                pass
            return
        except Exception:
            # fall through to console print if tkinter fails
            pass

    # fallback: console alert
    print("\n" + "="*40)
    print("!!! EAVESDROP ALERT !!!")
    print(text)
    print("="*40 + "\n")

# spawn popup safely
def spawn_alert_popup(data):
    t = threading.Thread(target=show_alert_popup, args=(data,), daemon=True)
    t.start()

# ---------- Socket.IO event handlers ----------
@sio.event
def connect():
    clear()
    print(f"[{DEVICE}] Connected to server")
    sio.emit("register", {"device_id": DEVICE})
    ask_send_loop()

@sio.on("registered")
def on_registered(p):
    print(f"[{DEVICE}] Registered: {p.get('device_id')}")

@sio.on("send_result")
def on_send_result(p):
    if not p.get("ok"):
        print("Send failed:", p.get("reason"))
    else:
        print("Send acknowledged, msg_id:", p.get("msg_id"))

@sio.on("incoming_locked")
def incoming_locked(payload):
    msg_id = payload.get("msg_id")
    sender = payload.get("from")
    print(f"\n🔔 Incoming locked message from {sender}.")
    print("Message is LOCKED 🔒 — Enter QKD 6-digit code to unlock.\n")
    attempts[msg_id] = 0
    ask_code(msg_id)

@sio.on("incoming_decrypted")
def incoming_decrypted(p):
    print("\n===== MESSAGE DELIVERED =====")
    print(p.get("plaintext"))
    print("=============================\n")
    # after receiving, prompt user whether they want to send
    ask_send_loop()

@sio.on("unlock_failed")
def unlock_failed(p):
    reason = p.get("reason")
    print("Unlock failed:", reason)
    if attempts:
        last_msg = list(attempts.keys())[-1]
        if attempts[last_msg] >= 3:
            print("Too many wrong attempts. Disconnecting.")
            sio.disconnect()
            sys.exit(0)
        else:
            remaining = 3 - attempts[last_msg]
            print(f"{remaining} attempts left.")
            ask_code(last_msg)
    else:
        print("No attempt record.")

@sio.on("alert_attack")
def alert_attack(payload):
    """
    Immediate alert handler — spawn a popup and print to console.
    Payload includes fields like: msg_id, from, to, label, p_attack, reason, QBER, etc.
    """
    print("\n!!! ALERT_ATTACK received from server !!!")
    # print short summary
    try:
        frm = payload.get("from")
        to = payload.get("to")
        reason = payload.get("reason", payload.get("detection_reason", ""))
        p_attack = payload.get("p_attack", "")
        print(f"From: {frm} -> To: {to}   reason: {reason}   p_attack: {p_attack}")
    except Exception:
        print(payload)
    # show GUI popup (non-blocking)
    spawn_alert_popup(payload)

# ---------- Sending / unlocking UI logic ----------
def ask_send_loop():
    # prompt once whenever appropriate
    while True:
        choice = input("\nDo you want to send a message? (yes/no): ").strip().lower()
        if choice == "yes":
            to = input("Send to device (A/B): ").strip().upper()
            if to not in ("A","B"):
                print("Invalid target. Use A or B.")
                continue
            msg = input("Enter your message: ").strip()
            if msg == "":
                print("Empty message aborted.")
                continue
            sio.emit("send_message", {"from": DEVICE, "to": to, "text": msg})
            print("Message sent (locked).")
            break
        elif choice == "no":
            print("Waiting for incoming messages...")
            break
        else:
            print("Please answer yes or no.")

def ask_code(msg_id):
    if attempts.get(msg_id, 0) >= 3:
        print("❌ Too many wrong attempts! Disconnecting…")
        sio.disconnect()
        sys.exit(0)

    code = input("Enter QKD 6-digit code: ").strip()
    attempts[msg_id] += 1
    sio.emit("unlock_attempt", {"device": DEVICE, "msg_id": msg_id, "code": code})
    # wait briefly for the server to respond
    time.sleep(0.5)

# ---------- disconnect handler ----------
@sio.event
def disconnect():
    print(f"[{DEVICE}] Disconnected")
    sys.exit(0)

# ---------- main ----------
def main():
    try:
        sio.connect(SERVER, transports=["websocket"])
        sio.wait()
    except KeyboardInterrupt:
        try:
            sio.disconnect()
        except:
            pass
        sys.exit(0)
    except Exception as e:
        print("Connection error:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
