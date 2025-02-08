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
import json
# from app.core.orchestrator import Orchestrator
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
        self.orchestrator = None 
        self.silence_duration = 0
    async def get_lead(self,dnid: str):
        """
        Fetches lead information associated with the provided DNID.

        :param dnid: The DNID to fetch lead information for.
        :return: JSON response with lead information.
        """
        try:
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
    def convert_wav_base64_to_ulaw_base64(self,wav_base64):
        """
        Convierte un archivo WAV en formato Base64 (PCM 16 bits) a u-law y lo codifica en Base64.

        :param wav_base64: String Base64 del archivo WAV original (PCM 16 bits).
        :return: String Base64 del archivo WAV convertido a u-law.
        """
        # Decodificar el Base64 a bytes WAV
        wav_bytes = base64.b64decode(wav_base64)

        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav_file:
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_rate = wav_file.getframerate()
            n_frames = wav_file.getnframes()

            # Leer datos PCM 16 bits
            pcm_bytes = wav_file.readframes(n_frames)

            # Convertir de PCM 16 bits a u-law
            ulaw_bytes = audioop.lin2ulaw(pcm_bytes, sample_width)

            # Crear un nuevo archivo WAV en formato u-law
            ulaw_buffer = io.BytesIO()
            with wave.open(ulaw_buffer, 'wb') as ulaw_wav:
                ulaw_wav.setnchannels(n_channels)  # Mono
                ulaw_wav.setsampwidth(1)  # u-law usa 8 bits (1 byte)
                ulaw_wav.setframerate(frame_rate)
                ulaw_wav.writeframes(ulaw_bytes)

            # Convertir a Base64 nuevamente
            return base64.b64encode(ulaw_buffer.getvalue()).decode('utf-8')
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
            # adjusted_duration = max(duration - 0.5, 0)
            adjusted_duration = max(duration, 0)

            return adjusted_duration
    def base64_wav_to_pcm(self, base64_string):
        """
        Convierte un archivo WAV en formato Base64 a bytes PCM sin encabezado WAV.
        
        :param base64_string: String en Base64 del archivo WAV.
        :return: Bytes PCM puros.
        """
        # Decodificar el string Base64 a bytes WAV
        wav_bytes = base64.b64decode(base64_string)

        # Cargar el WAV en un buffer de memoria
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav_file:
            # Obtener información del audio
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_rate = wav_file.getframerate()
            n_frames = wav_file.getnframes()

            # Leer los datos PCM (sin encabezado WAV)
            pcm_bytes = wav_file.readframes(n_frames)

        return pcm_bytes
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
        #debug
        #logger.debug("Customer call connected processing audio channel")
        client_ip = self.websocket.client.host
        client_port = self.websocket.client.port
        logger.warning(f"Cliente conectado desde {client_ip}:{client_port}")
        async for _ in self.process_stream():
            if self.stream_sid:
                logger.debug("stream_sid break")
                break

    async def process_stream(self):
        collected_checkpoints = []  # Lista para acumular los checkpoints

        try:
            while True:
                # Verificar si el WebSocket sigue conectado
                if not self.is_connected:
                    logger.debug("WebSocket is no longer connected, exiting loop.")
                    break
                
                try:
                    data = await self.websocket.receive()

                    # Salir del bucle si no se reciben datos
                    if not data:
                        logger.debug("No data received, exiting loop.")
                        break

                    
                    #debug
                    # logger.debug(f"Combined transcription: {combined}") 

                    # Procesar los datos recibidos
                    chunk = await self.handle_event(data)
                    if chunk:
                        yield chunk
                except Exception as e:
                    logger.error(f"Error procesando el flujo de audio: {e}")
                    raise e
            # Obtener los datos del almacenamiento local
            transcription_for_analysis_customer = LocalStorage.get(f"{self.call_sid}_transcription_for_analysis_customer", "")
            transcription_for_analysis_bot = LocalStorage.get(f"{self.call_sid}_transcription_for_analysis_bot", "")

            # Preparar y combinar los datos, asegurando que sean listas
            combined = self._prepare_and_combine(
                transcription_for_analysis_customer, transcription_for_analysis_bot
            )
            logger.warning(f"Chat combinado: {combined}")
            if combined is None:
                combined = []

        # Convert the list to a single string (joining with newline)
            combined_text = "\n".join(combined)  
            logger.warning(f"Chat combinado: {combined_text}")
            # Crear cliente para OpenAI
            llm = openai.AsyncClient()

            # Mensajes para el modelo
            messages = [
                {
                    "role": "system",
                    "content": """Analiza la conversación y devuelve un json con base a lo contestado por el cliente, identificando todos los puntos cumplidos.
                    En caso de no haberla requerido, devuelve un array vacio [].

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
                    "content": combined_text,
                },
            ]
            logger.warning(f"messages: {messages}")
            try:
                # Llamar al modelo para obtener la respuesta
                respuesta = await llm.chat.completions.create(
                    model="gpt-4-0125-preview",
                    temperature=0.1,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                # Extraer checkpoints de la respuesta
                logger.warning(f"Extraer checkpoints de la respuesta {respuesta.choices[0].message.content}")
                checkpoints = json.loads(respuesta.choices[0].message.content).get("checkpoints", [])
                collected_checkpoints.extend(checkpoints)  # Acumular checkpoints generados
            except Exception as e:
                logger.error(f"Error al procesar la respuesta del modelo: {e}")
                return
        except Exception as e:
            logger.error(f"Error general en process_stream: {e}")
            raise e
        if self.orchestrator:
            logger.warning(f"Códigos de estado: {json.dumps(collected_checkpoints)}")
            self.orchestrator.log(f"Códigos de estado: {json.dumps(collected_checkpoints)}")
        # Orchestrator.log(f"Códigos de estado: {json.dumps(collected_checkpoints)}");
        # Enviar todos los checkpoints acumulados al finalizar
        await self._send_collected_checkpoints(collected_checkpoints)

    async def _send_collected_checkpoints(self, checkpoints):
        """
        Envía todos los checkpoints acumulados en una sola solicitud HTTP.
        """
        if not isinstance(checkpoints, list):
            try:
                checkpoints = json.loads(checkpoints) if isinstance(checkpoints, str) else []
            except json.JSONDecodeError:
                checkpoints = []

        if not checkpoints:
            logger.debug("No checkpoints to send. Skipping HTTP request.")
            LocalStorage.set(f"{self.call_sid}_transcription_for_analysis_customer", "")
            LocalStorage.set(f"{self.call_sid}_transcription_for_analysis_bot", "")
            logger.debug("Local storage cleared even when no checkpoints were sent.")
            return
        conn = http.client.HTTPSConnection("app.ccc.uno")
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        dnid = f"{self.stream_sid}#{self.call_sid}#{self.number}"
        for checkpoint in checkpoints:
            payload = {
                "status": checkpoint,
                "callerid": dnid
            }
            data = json.dumps(payload)
            try:
                conn.request("POST", "/api/autoagent/call-state", body=data, headers=headers)
                response = conn.getresponse()
                logger.debug(f"Response from server: {response.status} {response.read().decode()}")
                logger.warning(f"Enviando a layer7 estado {checkpoint} con dnid {dnid}")
                self.orchestrator.log(f"Enviando a layer7 estado {checkpoint} con dnid {dnid}")
                if response.status == 200:
                    logger.debug("Checkpoints sent successfully.")
                else:
                    logger.error(f"Error en la solicitud HTTP. Status: {response.status}")
            except Exception as e:
                logger.error(f"Error al enviar datos al servidor: {e}")
            
                # Limpiar almacenamiento local independientemente del resultado
        LocalStorage.set(f"{self.call_sid}_transcription_for_analysis_customer", "")
        LocalStorage.set(f"{self.call_sid}_transcription_for_analysis_bot", "")
        logger.debug("Local storage cleared after attempting to send checkpoints.")
        conn.close()

    def _prepare_and_combine(self, customer_data, bot_data):
        """
        Convierte los datos recibidos a listas y los combina de forma segura.
        Siempre retorna una lista válida combinada.
        """
        def ensure_list(data):
            try:
                if isinstance(data, str) and data.strip():  # Si es un string no vacío
                    try:
                        # Intentar parsear como JSON primero
                        return json.loads(data)
                    except json.JSONDecodeError:
                        # Si no es JSON válido, encapsular el string en una lista
                        return [data]
                elif isinstance(data, list):  # Si ya es una lista
                    return data
                return []  # Cualquier otra cosa, lista vacía
            except Exception as e:
                logger.error(f"Error asegurando lista: {e} | Data: {data}")
                return []

        # Asegurar que ambos datos sean listas válidas
        customer_list = ensure_list(customer_data)
        bot_list = ensure_list(bot_data)

        # Combinar las listas
        return customer_list + bot_list


    async def handle_event(self, data):
        if 'text' in data:
            datos = data["text"].strip('"').strip()
            if re.match(self.pattern, datos):
                self.stream_sid, self.call_sid, self.number = datos.split('#')
                logger.warning(f"Codigo: {self.stream_sid}, Call ID: {self.call_sid}, Number: {self.number}")
                dnid=f"{self.stream_sid}%23{self.call_sid}%23{self.number}"
                # logger.debug(dnid)
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
    def detect_audio_format(self, data):
        try:
            # Intentar convertir desde µ-law a PCM 16-bit
            test_pcm = audioop.ulaw2lin(data[:10], 2)
            logger.debug("µ-law (necesita conversión a PCM)")
        except audioop.error:
            logger.debug("PCM (sin conversión adicional necesaria)")
            
    def calcular_umbral(self,audio_payload, sample_width=2):
        ruido_base = audioop.rms(audio_payload, sample_width)
        return max(ruido_base * 1.5, 500)  # Ajusta el factor 1.5 según el ruido
    
    async def process_media_event(self, data):
        # Assume `data` is already in bytes format
        audio_payload = data  # `data` is treated as Base64 bytes
        try:
            # Decode the Base64 payload
            # audio_content = base64.b64decode(audio_payload)
            
            # Convert from µ-law to PCM linear format
            # raw_audio_data = audioop.ulaw2lin(audio_payload, 2)
            raw_audio_data = audio_payload
            # self.detect_audio_format(data)
            umbral = self.calcular_umbral(audio_payload)
            rms = audioop.rms(audio_payload, 2)  # Calculate RMS
            # Check if the audio is loud enough and in "listening" state
            if rms > 350 and (self.switch == "listening" or self.switch is None):
                pcm = audioop.ulaw2lin(audio_payload, 2)
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, 'wb') as wf:
                    wf.setnchannels(1)  # Mono
                    wf.setsampwidth(2)  # PCM 16 bits usa 2 bytes por muestra
                    wf.setframerate(8000)  # Frecuencia de muestreo 8 kHz
                    wf.writeframes(pcm)  # Guardar datos PCM 16 bits

                # 📌 Guardar el audio en Base64 para enviarlo al frontend
                wav_buffer.seek(0)
                wav_data = wav_buffer.read()
                self.playsequence.append(raw_audio_data)
                self.silence_duration = 0
                return raw_audio_data
            else:
                self.silence_duration += self.duration
                if self.silence_duration >= 25.0:
                    self.silence_duration = 0
                    logger.warning("Más de 25 segundos de silencio detectados.")
                    await self.actions_call(self.call_sid,"hangup")

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
            byte_data = self.base64_wav_to_pcm(audio_data)
            self.playsequence.append(byte_data)
            self.silence_duration = 0
            await self.actions_call(self.call_sid,"playback",audio_data)
            self.silence_duration = 0
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
        #  return self.playsequence
        audio_bytes = b"".join(self.playsequence)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)  # Mono audio
            wf.setsampwidth(2)  # 2 bytes por muestra (16 bits)
            wf.setframerate(int(8000))  # Frecuencia de muestreo
            wf.writeframes(audio_bytes)

        wav_buffer.seek(0)
        wav_data = wav_buffer.read()
        base64_audio = [base64.b64encode(wav_data).decode("utf-8")]
        
        ulaw_base64_list = [self.convert_wav_base64_to_ulaw_base64(wav) for wav in base64_audio]
        # ulaw_base64_list = [self.convert_wav_base64_to_ulaw_base64(wav) for wav in self.playsequence]
        return ulaw_base64_list
        # if not self.playsequence:
        #     return [] # Evita errores si la lista está vacía
        # audio_bytes = b"".join(self.playsequence)
        # wav_buffer = io.BytesIO()
        # with wave.open(wav_buffer, 'wb') as wf:
        #     wf.setnchannels(1)  # Mono audio
        #     wf.setsampwidth(2)  # 2 bytes por muestra (16 bits)
        #     wf.setframerate(int(8000))  # Frecuencia de muestreo
        #     wf.writeframes(audio_bytes)

        # wav_buffer.seek(0)
        # wav_data = wav_buffer.read()
        # base64_audio = [base64.b64encode(audio_bytes).decode("utf-8")]
        # return base64_audio 