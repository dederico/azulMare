from .database import LocalStorage
from app.models.Config import Config
import random
import string

import io
import base64
import numpy as np
import struct

def decode_base64(base64_string):
    return base64.b64decode(base64_string)

def ulaw2lin(ulaw_byte):
    MULAW_BIAS = 200

    ulaw_byte = ~ulaw_byte
    sign = -1 if (ulaw_byte & 0x80) else 1
    exponent = (ulaw_byte >> 4) & 0x07
    mantissa = ulaw_byte & 0x0F

    sample = ((mantissa << 4) + MULAW_BIAS) << exponent
    return sign * (sample - MULAW_BIAS)


def decode_ulaw_to_pcm(ulaw_bytes):
    pcm_data = np.array([ulaw2lin(byte) for byte in ulaw_bytes], dtype=np.int16)
    return pcm_data


def create_wav_header(sample_rate, num_channels, bits_per_sample, data_length):
    header = bytearray(44)
    block_align = num_channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align

    struct.pack_into('<4sI4s4sIHHIIHH4sI', header, 0, b'RIFF', 36 + data_length, b'WAVE', b'fmt ', 16, 1,
                     num_channels, sample_rate, byte_rate, block_align, bits_per_sample, b'data', data_length)

    return header


def combine_audio_segments(base64_segments, sample_rate=8000, num_channels=1, bits_per_sample=16):
    decoded_segments = [decode_base64(segment) for segment in base64_segments]
    pcm_data = []

    for segment in decoded_segments:
        ulaw_data = np.frombuffer(segment, dtype=np.uint8)
        pcm_data.append(decode_ulaw_to_pcm(ulaw_data))

    pcm_data = np.concatenate(pcm_data)

    wav_header = create_wav_header(sample_rate, num_channels, bits_per_sample, len(pcm_data) * 2)
    wav_data = wav_header + pcm_data.tobytes()

    return wav_data

def isAPIEnabled():
    ls = LocalStorage()
    configs = { c.name: c.value for c in ls.GetAll(Config) }

    return configs.get("apiStatus", "false").lower() == "true"

def getAPIKey():
    ls = LocalStorage()
    configs = { c.name: c.value for c in ls.GetAll(Config) }

    return configs.get("apiKey", False)

def genAPIKey(length=128):
    ls = LocalStorage()
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for _ in range(length))