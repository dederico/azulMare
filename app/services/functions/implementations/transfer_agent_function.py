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
def calculate_wav_duration_from_base64(base64_audio: str) -> float:
        """
        Calcula la duración de un archivo WAV a partir de su representación Base64.

        :param base64_audio: Cadena Base64 que representa un archivo WAV.
        :return: Duración del archivo WAV en segundos.
        """
        # Decodificar Base64 a bytes
        wav_bytes = base64.b64decode(base64_audio)

        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            frame_rate = wf.getframerate()
            n_frames = wf.getnframes()
            duration = n_frames / float(frame_rate)
        
        return max(duration, 0)
    
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
    
    # Eliminar comillas extras si las hay y validar ID
    try:
        call_id = int(call_sid.strip('"'))
    except ValueError:
        logger.error(f"Invalid call_sid: {call_sid}. Cannot convert to integer.")
        return "Error: call_sid inválido"

    current_dir = os.path.dirname(os.path.abspath(__file__))
    wav_path = os.path.join(current_dir, "files", "actions_call_transfer.wav")

    try:
        # Leer archivo WAV de forma asíncrona
        wav_data = await asyncio.to_thread(lambda: open(wav_path, "rb").read())

        # Convertir a Base64 en un hilo separado
        audio_base64 = await asyncio.to_thread(base64.b64encode, wav_data)
        audio_base64 = audio_base64.decode("utf-8")

        payload = {
            "call_id": call_id,
            "action": "playback",
            "data": {"audio_base64": audio_base64}
        }

        async with httpx.AsyncClient() as client:
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            
            duration = calculate_wav_duration_from_base64(audio_base64)

            # Primera solicitud para reproducir el audio
            logger.debug("Enviando solicitud para reproducir el audio antes de transferir")
            response = await client.post("https://websockets.ccc.uno/api/v1/autoagent", json=payload, headers=headers)
            logger.debug(f"Playback response status: {response.status_code}")
            logger.debug(f"Response body: {response.text}")

            await asyncio.sleep(duration) 

            # Segunda solicitud para realizar la transferencia
            transfer_payload = {"call_id": call_id, "action": "transfer_agent"}
            logger.debug("Enviando solicitud para transferir la llamada")
            response = await client.post("https://websockets.ccc.uno/api/v1/autoagent", json=transfer_payload, headers=headers)
            logger.debug(f"Transfer response status: {response.status_code}")
            logger.debug(f"Transfer response body: {response.text}") 

        return "Se inició la transferencia al agente humano de manera exitosa."

    except Exception as e:
        logger.error(f"Error en la función de transferencia: {str(e)}")
        return f"Error al intentar transferir la llamada: {str(e)}"
