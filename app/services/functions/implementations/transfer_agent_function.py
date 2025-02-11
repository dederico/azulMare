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
    
async def actions_call_transfer(call_sid: str):
    """Transferir al usuario si asi lo solicita.

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.

    Returns:
        A confirmation message indicating the transfer.
    """
    logger.debug(f"ADENTRO DE LA FUNCION transfer_agent_function actions_call_transfer called with call_sid: {call_sid}")

    if not call_sid:
        logger.error("actions_call_transfer called without call_sid")
        return "Error: No se proporcionó call_sid"
    
    # Eliminar comillas extras si las hay
    call_sid = call_sid.strip('"')

    try:
        # Preparar el audio para reproducir antes de transferir
        current_dir = os.path.dirname(os.path.abspath(__file__))
        wav_path = os.path.join(current_dir, "files", "transferir.wav")

        with open(wav_path, "rb") as wav_file:
            wav_data = wav_file.read()
        
        audio_base64 = base64.b64encode(wav_data).decode(encoding="utf-8")
        
        # Reproducir el audio
        payload = {
            "call_id": int(call_sid),
            "action": "playback",
            "data": {"audio_base64": audio_base64}
        }

        conn = http.client.HTTPSConnection("websockets.ccc.uno")
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        
        data = json.dumps(payload)
        conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
        response = conn.getresponse()
        logger.debug(f"Playback response status: {response.status}")
        logger.debug(response.read().decode())

        # Esperar a que se reproduzca el audio (ajusta este tiempo según sea necesario)
        await asyncio.sleep(5)

        # Realizar la transferencia
        transfer_payload = {
            "call_id": int(call_sid),
            "action": "transfer_agent"
        }
        
        data = json.dumps(transfer_payload)
        conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
        response = conn.getresponse()
        logger.debug(f"Transfer response status: {response.status}")
        logger.debug(response.read().decode())

        Orchestrator.staticlog(call_sid, "Transferencia al agente humano iniciada")

        return "Se inició la transferencia al agente humano de manera exitosa."
    except Exception as e:
        logger.error(f"Error en la función de transferencia: {str(e)}")
        return f"Error al intentar transferir la llamada: {str(e)}"
