# qkd_sim.py
"""
A simple BB84-like QKD simulator.
Generates:
 - sifted_key_alice: list of 0/1 bits
 - qber
 - timing_jitter
 - detector_temp
 - signal_intensity
"""

import random
import math
import numpy as np


def simulate_bb84(
    n_bits=512,
    base_mismatch_noise=0.005,
    detector_noise=0.001,
    eavesdrop=False,
    eavesdrop_rate=0.0
):
    """
    Basic QKD simulation:
    - Generate random bits.
    - Apply noise and optional Eve disturbance.
    """

    # random raw bits
    alice_raw = [random.randint(0, 1) for _ in range(n_bits)]
    bob_raw = alice_raw.copy()

    # introduce detector noise
    for i in range(n_bits):
        if random.random() < detector_noise:
            bob_raw[i] ^= 1  # flip due to detector noise

    # eavesdrop disturbance
    if eavesdrop and eavesdrop_rate > 0:
        for i in range(n_bits):
            if random.random() < eavesdrop_rate:
                bob_raw[i] ^= 1

    # sifted key: random subset (simulate basis matching)
    sifted_indices = [i for i in range(n_bits) if random.random() > 0.5]
    sifted_key_alice = [alice_raw[i] for i in sifted_indices]
    sifted_key_bob = [bob_raw[i] for i in sifted_indices]

    # compute QBER
    if len(sifted_key_alice) == 0:
        qber = 0.5
    else:
        mism = sum(1 for a, b in zip(sifted_key_alice, sifted_key_bob) if a != b)
        qber = mism / len(sifted_key_alice)

    # physical metrics
    timing_jitter = np.random.normal(0, 0.002)
    signal_intensity = np.random.normal(1.0, 0.0005)
    detector_temp = np.random.normal(20.0, 0.5)

    return {
        "sifted_key_alice": sifted_key_alice,
        "qber": float(qber),
        "timing_jitter": float(timing_jitter),
        "signal_intensity": float(signal_intensity),
        "detector_temp": float(detector_temp)
    }


def bytes_to_bits(b: bytes):
    """
    Convert bytes -> list[int] bits (MSB first)
    """
    bits = []
    for byte in b:
        for bit_pos in range(7, -1, -1):
            bits.append((byte >> bit_pos) & 1)
    return bits
