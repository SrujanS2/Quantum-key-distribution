# key_manager.py
"""
Simple in-memory key buffer manager. Each device has a bit buffer (list of ints).
Used optionally by server when doing OTP from pre-buffered key bits.
"""

from typing import Dict, List

_buffers: Dict[str, List[int]] = {}

def add_key_bits(device: str, bits: List[int]):
    _buffers.setdefault(device, []).extend(bits)

def available_key_bits(device: str) -> int:
    return len(_buffers.get(device, []))

def consume_key_bits(device: str, n_bits: int) -> List[int]:
    buf = _buffers.get(device, [])
    if len(buf) < n_bits:
        raise ValueError("Not enough key bits")
    out = buf[:n_bits]
    _buffers[device] = buf[n_bits:]
    return out
