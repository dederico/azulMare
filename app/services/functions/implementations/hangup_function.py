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
    
# async def actions_call(call_sid: str):
#         """Terminar interaccion si el usuario asi lo solicita.

#         Args:
#             call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.

#         Returns:
#             A confirmation message indicating the hangup.

#         """
#         #logger.debug(f"ADENTRO DE LA FUNCION hangup_function actions_call called with call_sid: {call_sid}")

#         # if not call_sid:
#         #         #logger.error("actions_call called without call_sid")
#         #         return "Error: No se proporcionó call_sid"
        
#         payload=None
#         duration=None
#         current_dir = os.path.dirname(os.path.abspath(__file__))  # Carpeta actual
#         wav_path = os.path.join(current_dir, "files", "colgar.wav")

#         with open(wav_path, "rb") as wav_file:
#                 wav_data = wav_file.read()
        
#         audio_base64 = base64.b64encode(wav_data).decode(encoding="utf-8")
#         payload = {
#                 "call_id": int(call_sid),
#                 "action": "playback",
#                 "data": {"audio_base64": f"{audio_base64}"}
#         }

#         #logger.debug(f"Inside the hangup function Payload prepared: {call_sid}")


#         conn = http.client.HTTPSConnection("websockets.ccc.uno")
#         params = payload  # Parámetros de consulta
#         headers = {"accept": "application/json","Content-Type": "application/json"}  # Encabezados
#         duration = calculate_wav_duration_from_base64(audio_base64)
#         data = json.dumps(params)
        
#         #logger.debug("Sending first request to play audio")
#         conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
#         response = conn.getresponse()
#         #logger.debug(response.status)
#         #logger.debug(response.read().decode())

#         Orchestrator.staticlog(call_sid, "Claro!, muchas gracias por tu tiempo -- COLGAR")
#         await asyncio.sleep(duration)
                
#         payload = {
#                 "call_id": int(call_sid),
#                 "action": "hangup"
#                 }
#         params = payload  # Parámetros de consulta
#         data = json.dumps(params)

#         #logger.debug("Sending second request to hangup")
#         conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
#         response = conn.getresponse()
#         #logger.debug(response.status)
#         #logger.debug(response.read().decode())

#         return "Se colgó la llamada de manera exitosa."

async def actions_call(call_sid: str):
    """Terminar interaccion si el usuario asi lo solicita.

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.

    Returns:
        A confirmation message indicating the hangup.

    """
    logger.debug(f"ADENTRO DE LA FUNCION hangup_function actions_call called with call_sid: {call_sid}")

    if not call_sid:
        logger.error("actions_call called without call_sid")
        return "Error: No se proporcionó call_sid"
    
    # Asegurarse de que call_sid sea un entero
    try:
        call_id = int(call_sid.strip('"'))  # Eliminar comillas extras si las hay y convertir a entero
    except ValueError:
        logger.error(f"Invalid call_sid: {call_sid}. Cannot convert to integer.")
        return "Error: call_sid inválido"

    payload = None
    duration = None
    current_dir = os.path.dirname(os.path.abspath(__file__))  # Carpeta actual
    wav_path = os.path.join(current_dir, "files", "colgar.wav")

    with open(wav_path, "rb") as wav_file:
        wav_data = wav_file.read()
    
    audio_base64 = base64.b64encode(wav_data).decode(encoding="utf-8")
    payload = {
        "call_id": call_id,  # Usar el call_id convertido
        "action": "playback",
        "data": {"audio_base64": audio_base64}
    }

    logger.debug(f"Inside the hangup function Payload prepared: {call_id}")

    conn = http.client.HTTPSConnection("websockets.ccc.uno")
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    duration = calculate_wav_duration_from_base64(audio_base64)
    data = json.dumps(payload)
    
    logger.debug("Sending first request to play audio")
    conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
    response = conn.getresponse()
    logger.debug(f"Response status: {response.status}")
    logger.debug(f"Response body: {response.read().decode()}")

    Orchestrator.staticlog(str(call_id), "Claro!, muchas gracias por tu tiempo -- COLGAR")
    await asyncio.sleep(duration)
            
    hangup_payload = {
        "call_id": call_id,
        "action": "hangup"
    }
    hangup_data = json.dumps(hangup_payload)

    logger.debug("Sending second request to hangup")
    conn.request("POST", "/api/v1/autoagent", body=hangup_data, headers=headers)
    response = conn.getresponse()
    logger.debug(f"Hangup response status: {response.status}")
    logger.debug(f"Hangup response body: {response.read().decode()}")

    return "Se colgó la llamada de manera exitosa."