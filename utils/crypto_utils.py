# crypto_utils.py
#Simple OTP helper functions (bits/bytes conversions and OTP xor).
from typing import List

def bytes_to_bits(b: bytes) -> List[int]:
    bits = []
    for byte in b:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits

def bits_to_bytes(bits: List[int]) -> bytes:
    if len(bits) % 8 != 0:
        bits = bits + [0] * (8 - (len(bits) % 8))
    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for bit in bits[i:i+8]:
            byte = (byte << 1) | int(bit)
        out.append(byte)
    return bytes(out)

def otp_encrypt(msg_bytes: bytes, key_bits: List[int]) -> bytes:
    if len(key_bits) < len(msg_bytes) * 8:
        raise ValueError("Not enough key bits")
    kb = bits_to_bytes(key_bits[:len(msg_bytes)*8])
    return bytes([mb ^ kb[i] for i, mb in enumerate(msg_bytes)])

def otp_decrypt(cipher_bytes: bytes, key_bits: List[int]) -> bytes:
    if len(key_bits) < len(cipher_bytes) * 8:
        raise ValueError("Not enough key bits")
    kb = bits_to_bytes(key_bits[:len(cipher_bytes)*8])
    return bytes([cb ^ kb[i] for i, cb in enumerate(cipher_bytes)])
