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
import openai
from app.util.database import LocalStorage
class WebSocketHandler:
    duration = 0.02

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_sid = None
        self.initial_data = None
        self.switch = None
        self.playsequence = []
        self.number=None
        self.call_sid=None
        self.pattern=r"^[a-zA-Z0-9]+#[a-zA-Z0-9]+#[a-zA-Z0-9]+$"
    async def get_lead(self,dnid: str):
        """
        Fetches lead information associated with the provided DNID.

        :param dnid: The DNID to fetch lead information for.
        :return: JSON response with lead information.
        """
        try:
            logger.debug(dnid)
            endpoint_url = f"https://app.ccc.uno/api/autoagent/{dnid}"

            async with httpx.AsyncClient() as client:
                response = await client.get(endpoint_url)
                response.raise_for_status()

            lead_info = response.json()
            logger.debug(f"Lead information retrieved: {lead_info}")
            return lead_info
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch lead information: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=response.status_code, detail=f"Error from lead service: {e.response.text}")
    def calculate_wav_duration_from_base64(self,base64_audio: str) -> float:
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
            adjusted_duration = max(duration - 0.5, 0)
            print(f"Frecuencia de muestreo: {frame_rate} Hz")
            print(f"Número de frames: {n_frames}")
            print(f"Número de canales: {channels}")
            print(f"Ancho de muestra: {sample_width} bytes")
            print(f"Duración calculada: {duration:.2f} segundos")

            return adjusted_duration
    async def actions_call(self,call_id: str,action:str,data:bytes=None):
        """
        Ends an active call associated with the specified call_id.

        :param call_id: The ID of the ongoing call.
        :param action: The action to execute, can be hangup,transfer_agent or playback 
        :return: JSON response confirming the hangup.
        """
        payload=None
        duration=None
        if data:
            # audio_base64 = base64.b64encode(data).decode(encoding="utf-8")
            payload = {
                "call_id": int(call_id),
                "action": action,
                "data": {"audio_base64": f"{data}"}
            }
        else:
            payload = {
                "call_id": int(call_id),
                "action": action
            }
        logger.debug(f"{call_id}")
        conn = http.client.HTTPSConnection("websockets.ccc.uno")
        params = payload  # Parámetros de consulta
        headers = {"accept": "application/json","Content-Type": "application/json"}  # Encabezados
        if data:
            duration = self.calculate_wav_duration_from_base64(data)
        data = json.dumps(params)
        
        conn.request("POST", "/api/v1/autoagent", body=data, headers=headers)
        response = conn.getresponse()
        logger.debug(response.status)
        logger.debug(response.read().decode())
        if duration:
            await asyncio.sleep(duration)
    
    async def connect(self):
        await self.websocket.accept()

        logger.debug("Customer call connected processing audio channel")
        async for _ in self.process_stream():
            if self.stream_sid:
                logger.debug("stream_sid break")
                break

    async def process_stream(self):
        try:
            transcription_for_analysis_customer = LocalStorage.get("transcription_for_analysis_customer", "")
            transcription_for_analysis_bot = LocalStorage.get("transcription_for_analysis_bot", "")
            
            while self.websocket.connected:
                try:
                    # Recibir datos del WebSocket
                    data = await self.websocket.receive()
                    
                    # Salir del bucle si no se reciben datos
                    if not data:
                        logger.debug("No data received, exiting loop.")
                        break

                    logger.debug(f"Using shared transcription: {transcription_for_analysis_customer}")
                    logger.debug(f"Using this text: {transcription_for_analysis_bot}")

                    # Procesar los datos recibidos
                    chunk = await self.handle_event(data)
                    if chunk:
                        yield chunk
                except Exception as e:
                    logger.error(f"Error procesando el flujo de audio: {e}")
                    raise e

            # Crear cliente para OpenAI
            llm = openai.AsyncClient()

            # Validar y combinar transcription y text
            if isinstance(transcription_for_analysis_customer, list) and isinstance(transcription_for_analysis_bot, list):
                combined = transcription_for_analysis_customer + transcription_for_analysis_bot
            else:
                logger.error("Transcription and text must be lists. Found: %s, %s", type(transcription_for_analysis_customer), type(transcription_for_analysis_bot))
                return

            # Mensajes para el modelo
            messages = [
                {
                    "role": "system",
                    "content": """Analiza la conversacion y devuelve un json con base a lo contestado por el cliente, identificando todos los puntos cumplidos.
                    En caso de no haberla requerido, devuelve un false.

                    * STC-100: Si el cliente contesta.
                    * STC-105: Si el cliente contesta, y no confirma identidad.    
                    * STC-110: Si el cliente contesta, y confirma identidad.
                    * STC-115: Si el cliente contesta, no confirma identidad, y no conoce al cliente.
                    * STC-120: Si el cliente contesta, no confirma identidad, pero conoce al cliente.
                    * STC-125: Si el cliente contesta, confirma identidad y paga el día de hoy.
                    * STC-130: Si el cliente contesta, confirma identidad, y no puede pagar hoy.
                    * STC-135: Si el cliente contesta, confirma identidad, y no puede pagar antes de la fecha límite.
                    * STC-140: Si el cliente contesta, confirma identidad, y puede pagar antes de la fecha límite.
                    * STC-145: Si el cliente contesta, confirma identidad, no puede pagar antes de la fecha límite, y es transferido a un agente.
                    
                    Ejemplo
                    
                    {{
                        "checkpoints": ["STC-100","STC-110","STC-120"]
                    }}
                    """,
                },
                {
                    "role": "user",
                    "content": json.dumps(combined, indent=2),
                },
            ]

            try:
                # Llamar al modelo para obtener la respuesta
                respuesta = await llm.chat.completions.create(
                    model="gpt-4-0125-preview",
                    temperature=0.1,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                # Extraer checkpoints de la respuesta
                checkpoints = json.loads(respuesta.choices[0].message.content).get("checkpoints", [])
            except Exception as e:
                logger.error(f"Error al procesar la respuesta del modelo: {e}")
                return

            # Formatear el identificador del cliente
            dnid = f"{self.stream_sid}%23{self.call_sid}%23{self.number}"

            # Configurar conexión HTTP
            conn = http.client.HTTPSConnection("app.ccc.uno")
            headers = {"accept": "application/json", "Content-Type": "application/json"}

            try:
                # Enviar cada checkpoint como payload
                for checkpoint in checkpoints:
                    payload = {
                        "status": checkpoint,
                        "callerid": dnid
                    }
                    data = json.dumps(payload)

                    conn.request("POST", "/api/autoagent/call-state", body=data, headers=headers)
                    response = conn.getresponse()
                    logger.debug(f"Response from server: {response.status} {response.read().decode()}")

                    if response.status != 200:
                        logger.error(f"Error en la solicitud HTTP. Status: {response.status}")
            except Exception as e:
                logger.error(f"Error al enviar datos al servidor: {e}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error general en process_stream: {e}")
            raise e



    async def handle_event(self, data):
        if 'text' in data:
            datos = data["text"].strip('"').strip()
            if re.match(self.pattern, datos):
                self.stream_sid, self.call_sid, self.number = datos.split('#')
                logger.warning(f"Codigo: {self.stream_sid}, Call ID: {self.call_sid}, Number: {self.number}")
                dnid=f"{self.stream_sid}%23{self.call_sid}%23{self.number}"
                logger.debug(dnid)
                context=await self.get_lead(dnid=dnid)
                logger.warning(f"context: {context}")
                self.initial_data=context
        elif 'bytes' in data:
            datos= data["bytes"]
            return await self.process_media_event(datos)
             
        # if data["event"] == "start":
        #     self.initial_data = data["start"]
        #     self.stream_sid = data["streamSid"]
        #     self.call_sid = data["start"]["callSid"]

        # elif data["event"] == "media":
        #     return await self.process_media_event(data)

        # elif data["event"] == "mark":
        #     self.switch = data["mark"]["name"]

    async def process_media_event(self, data):
        # Assume `data` is already in bytes format
        audio_payload = data  # `data` is treated as Base64 bytes
        try:
            # Decode the Base64 payload
            # audio_content = base64.b64decode(audio_payload)
            
            # Convert from µ-law to PCM linear format
            # raw_audio_data = audioop.ulaw2lin(audio_payload, 2)
            raw_audio_data = audio_payload
            rms = audioop.rms(raw_audio_data, 2)  # Calculate RMS
            # Check if the audio is loud enough and in "listening" state
            if rms > 300 and (self.switch == "listening" or self.switch is None):
                self.playsequence.append(audio_payload)  # Append the raw payload
                return raw_audio_data
            else:
                # Generate silence if below threshold or not in listening state
                raw_audio_data = await self.generate_silence()
                return raw_audio_data
        except (binascii.Error, ValueError) as e:
            # Handle invalid Base64 or decoding errors
            logger.error(f"Error decoding Base64: {e}")
            return await self.generate_silence()

    async def generate_silence(self, sample_width=2, sample_rate=8000):
        # logger.debug("Generating and forwarding silence frame")
        num_samples = int(self.duration * sample_rate)
        silence_data = b"\x00" * (num_samples * sample_width)
        return audioop.lin2ulaw(silence_data, sample_width)

    async def send_audio(self, audio_data):
        logger.debug("Received audio frame from Robot")
        if self.is_connected:
            logger.debug("Socket is connected, sending audio frame to customer")
            self.playsequence.append(audio_data)
            await self.actions_call(self.call_sid,"playback",audio_data)
            # await self.websocket.send_json(
            #     {
            #         "event": "media",
            #         "streamSid": self.stream_sid,
            #         "media": {"payload": audio_data},
            #     }
            # )
        else:
            logger.debug("User is not connected anymore skipping audio sending to customer")

    async def send_mark(self, mark):
        logger.debug("Sending {} mark to Twilio".format(mark))
        if self.is_connected:
            self.switch=mark
            # await self.websocket.send_json(
            #     {
            #         "event": "mark",
            #         "streamSid": self.stream_sid,
            #         "mark": {"name": mark},
            #     }
            # )
        else:
            logger.debug("Socket not connected hence mark Not_Sent")

    @property
    def is_connected(self):
        return (
            self.websocket.application_state == WebSocketState.CONNECTED
            and self.websocket.client_state == WebSocketState.CONNECTED
        )
    
    @property
    def audio_sequence(self):
        return self.playsequence