import base64
import audioop
import re
import httpx
import http.client
import json
from fastapi import WebSocket,HTTPException
from app.util.logger import logger
from fastapi.websockets import WebSocketState
from starlette.websockets import WebSocketDisconnect
import io
from pydub import AudioSegment
import binascii
import wave
import asyncio
import os
from app.core.orchestrator import Orchestrator
def calculate_wav_duration_from_base64(base64_audio: str) -> float:
        """
        Calcula la duración de un archivo WAV a partir de su representación Base64.

        :param base64_audio: Cadena Base64 que representa un archivo WAV.
        :return: Duración del archivo WAV en segundos.
        """
        # Decodificar Base64 a bytes
        wav_bytes = base64.b64decode(base64_audio)

        # Leer el archivo WAV desde los bytes decodificados
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            frame_rate = wf.getframerate()  # Frecuencia de muestreo (Hz)
            n_frames = wf.getnframes()  # Número total de frames
            channels = wf.getnchannels()  # Número de canales
            sample_width = wf.getsampwidth()  # Ancho de muestra en bytes

            # Calcular duración
            duration = n_frames / float(frame_rate)
            adjusted_duration = max(duration, 0)
          
            return adjusted_duration
    
async def actions_call(call_sid: str):
        """
        Ends an active call associated with the specified call_sid.

        :param call_sid: The ID of the ongoing call.
        :return: JSON response confirming the hangup. 

        """ 
        payload=None
        duration=None
        current_dir = os.path.dirname(os.path.abspath(__file__))  # Carpeta actual
        wav_path = os.path.join(current_dir, "files", "colgar.wav")
        with open(wav_path, "rb") as wav_file:
                wav_data = wav_file.read()
        
        audio_base64 = base64.b64encode(wav_data).decode(encoding="utf-8")
        payload = {
                "call_id": int(call_sid),
                "action": "playback",
                "data": {"audio_base64": f"{audio_base64}"}
            }
    
        conn = http.client.HTTPSConnection("websockets.ccc.uno")
        params = payload  # Parámetros de consulta
        headers = {"accept": "application/json","Content-Type": "application/json"}  # Encabezados
        duration = calculate_wav_duration_from_base64(audio_base64)
        data = json.dumps(params)
        
        conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
        response = conn.getresponse()
        logger.debug(response.status)
        logger.debug(response.read().decode())
        Orchestrator.staticlog(call_sid, "Claro!, te transfiero con uno de mis compañeros -- COLGAR")
        await asyncio.sleep(duration)
                
        payload = {
                "call_id": int(call_sid),
                "action": "hangup"
                }
        params = payload  # Parámetros de consulta
        data = json.dumps(params)
        
        conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
        response = conn.getresponse()
        logger.debug(response.status)
        logger.debug(response.read().decode())
