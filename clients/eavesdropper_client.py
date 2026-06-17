"""
Passive eavesdropper client with Aggressive Attack capabilities
- Registers as 'E'
- Listens for 'alert_attack' and other server events
- Allows user to toggle 'Aggressive Attack' mode on the server
"""

import argparse
import socketio
import sys
import threading
import time

parser = argparse.ArgumentParser()
parser.add_argument("--server", required=True)
args = parser.parse_args()

SERVER = args.server.rstrip("/")
sio = socketio.Client()
DEVICE = "E"

@sio.event
def connect():
    print("[E] Connected to server")
    sio.emit("register", {"device_id": DEVICE})

@sio.on("registered")
def on_registered(p):
    print(f"[E] Registered: {p}")

@sio.on("alert_attack")
def on_alert(p):
    print("\n[ALERT] Eavesdropping detected by server:")
    
    if "narrative" in p:
        print(p["narrative"])
    else:
        # Fallback for older server versions
        for k,v in p.items():
            print(f"  {k}: {v}")
            
    print("\nCommand (start/stop/quit): ", end="", flush=True)

@sio.on("incoming_locked")
def on_incoming_locked(p):
    print(f"\n[E] incoming_locked: {p}")
    print("Command (start/stop/quit): ", end="", flush=True)

@sio.on("send_result")
def on_send_result(p):
    print(f"\n[E] send_result: {p}")
    print("Command (start/stop/quit): ", end="", flush=True)

@sio.on("attack_status")
def on_attack_status(p):
    print(f"\n[E] Attack Status Changed: {p}")
    print("Command (start/stop/quit): ", end="", flush=True)

@sio.event
def disconnect():
    print("[E] Disconnected")

def input_loop():
    time.sleep(1) # wait for connection
    print("\n--- Eavesdropper Control ---")
    print("Commands:")
    print("  start : Trigger Aggressive Attack Mode (Force Detection)")
    print("  stop  : Stop Attack Mode")
    print("  quit  : Exit")
    print("----------------------------")
    
    while True:
        try:
            cmd = input("Command (start/stop/quit): ").strip().lower()
            if cmd == "start":
                print("[E] Requesting Aggressive Attack...")
                sio.emit("attack_start", {"device": DEVICE})
            elif cmd == "stop":
                print("[E] Stopping Attack...")
                sio.emit("attack_stop", {"device": DEVICE})
            elif cmd == "quit":
                print("[E] Quitting...")
                sio.disconnect()
                break
            else:
                if cmd: print("Unknown command.")
        except EOFError:
            break

def main():
    try:
        sio.connect(SERVER, transports=["websocket"])
    except Exception as e:
        print("Connection error:", e); return

    # Start input loop in a separate thread so socketio can handle events
    t = threading.Thread(target=input_loop)
    t.daemon = True
    t.start()

    try:
        sio.wait()
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        try:
            sio.disconnect()
        except:
            pass
        sys.exit(0)

if __name__ == "__main__":
    main()
