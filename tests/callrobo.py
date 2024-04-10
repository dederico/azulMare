import json
import audioop
import websocket
import numpy as np
from time import sleep
from random import choices
from threading import Thread
from pyaudio import PyAudio, paInt16
from base64 import b64encode, b64decode
from string import ascii_letters, digits

SILENCE_THRESHOLD = 1000
CHUNK = 1024
ringer = 1

args = {
    "rate": 8000,
    "channels": 1,
    "input": True,
    "output": True,
    "format": paInt16,
    "frames_per_buffer": CHUNK
}

p = PyAudio()
stream = p.open(**args)

call_sid = ''.join(choices(ascii_letters + digits, k=24))
stream_sid = ''.join(choices(ascii_letters + digits, k=24))

def generate_tone(frequency, duration, rate):
    num_samples = int(duration * rate)
    time_axis = np.linspace(0, duration, num_samples)
    tone = np.sin(2 * np.pi * frequency * time_axis)
    return (tone * 32767).astype(np.int16)

def play_tone(frequency=440, duration=1, gap=1.5):
    global stream
    failed = 0
    while ringer in [-1, 1]:
        if ringer == 1:
            tone = generate_tone(frequency, duration, args['rate'])
            stream.write(tone.tobytes())
            sleep(gap)
        else:
            tone = generate_tone(frequency - 40, duration - 0.5, args['rate'])
            stream.write(tone.tobytes())
            sleep(gap - 1.2)
            failed += 1
            if failed == 4:
                break

def stream_mic(ws):
    data = stream.read(CHUNK)
    audio = audioop.lin2ulaw(data, 2)
    while audioop.rms(audio, 2) >= SILENCE_THRESHOLD:
        ws.send(json.dumps({
            "event": "media",
            "media": {
                "payload": b64encode(audio).decode("utf-8")
            },
            "streamSid": stream_sid
        }))
        data = stream.read(CHUNK)
        audio = audioop.lin2ulaw(data, 2)

def stream_speaker(ws):
    global ringer
    payload = {
        "event": "start",
        "start": {
            "callSid": call_sid
        },
        "debug": True,
        "streamSid": stream_sid
    }

    ws.send(json.dumps(payload))
    print("Conversation Initiated")

    while True:
        try:
            message = ws.recv()
            data = json.loads(message)
            if data['event'] == 'media':
                ringer = 0
                audio_payload = data["media"]["payload"]
                audio_content = b64decode(audio_payload)
                raw_audio_data = audioop.ulaw2lin(audio_content, 2)
                stream.write(raw_audio_data)
        except websocket.WebSocketException:         
            break

ringThread = Thread(target=play_tone)
ringThread.start();

def main():
    tasks = []
    ws = websocket.create_connection("ws://localhost:8000/stream")

    tasks.append(Thread(target=stream_speaker, args=(ws,)))
    tasks.append(Thread(target=stream_mic, args=(ws,)))
    
    if ws.connected:
        for t in tasks:
            t.start()
        for t in tasks:
            t.join()

try:
    main()
except Exception as e:
    ringer = -1
finally:
    ringThread.join()
    stream.stop_stream()
    stream.close()
    p.terminate()