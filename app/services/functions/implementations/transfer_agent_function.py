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


async def actions_call_transfer(call_sid: str):
        """
        Ends an active call associated with the specified call_id.

        :param call_id: The ID of the ongoing call.
        :return: JSON response confirming the hangup. 

        """ 
        payload=None
        duration=None
        # if data:
        #     # audio_base64 = base64.b64encode(data).decode(encoding="utf-8")
        #     payload = {
        #         "call_id": int(call_id),
        #         "action": action,
        #         "data": {"audio_base64": f"{data}"}
        #     }
        # else: 
        payload = {
                "call_id": int(call_sid),
                "action": "transfer_agent"
                }
        logger.debug(f"{call_sid}")
        conn = http.client.HTTPSConnection("websockets.ccc.uno")
        params = payload  # Parámetros de consulta
        headers = {"accept": "application/json","Content-Type": "application/json"}  # Encabezados
        # if data:
        #     duration = self.calculate_wav_duration_from_base64(data)
        data = json.dumps(params)
        
        conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
        response = conn.getresponse()
        logger.debug(response.status)
        logger.debug(response.read().decode())
        # if duration:
        #     await asyncio.sleep(duration)
