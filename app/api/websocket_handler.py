import base64
import audioop
import re
import httpx
import http.client
import json
from fastapi import WebSocket,HTTPException
from app.util.logger import logger
from fastapi.websockets import WebSocketState
import io
import os
import binascii
import wave
import asyncio
import openai
from app.util.database import LocalStorage
import json
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
from pathlib import Path 
import unicodedata
import traceback
# from app.core.orchestrator import Orchestrator
class WebSocketHandler:
    duration = 0.02
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_sid = None
        self.initial_data = None 
        self.switch = "not_listening"
        self.playsequence = []
        self.number=None
        self.call_sid=None
        self.pattern=r"^[a-zA-Z0-9]+#[a-zA-Z0-9]+#[a-zA-Z0-9]+$"
        self.orchestrator = None 
        self.silence_duration = 0
        self.queue = asyncio.Queue()
        self.now = datetime.now(ZoneInfo("America/Mexico_City"))
        self.queue_task = asyncio.create_task(self.process_queue())
        self.para_colgar = ["excelente dia"]
        self.para_transferir = ["sigue en la linea"]
    def remove_accents(self, text):
        return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

    def clean_text(self, text):
        text = unicodedata.normalize("NFKC", text).strip().lower()
        text = self.remove_accents(text)  # Elimina tildes
        text = text.replace("\n", " ").replace("\t", " ").replace("  ", " ")
        return text
    def normalize_text(self,text):
        return unicodedata.normalize("NFKC", text).strip().lower()
    def gettime(self):
        return datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
    async def transfer_function(self):
        if not self.call_sid:
            logger.error("actions_call_transfer called without call_sid")
            return "Error: No se proporcionó call_sid"
        
        # Eliminar comillas extras si las hay y validar ID
        try:
            call_id = int(self.call_sid.strip('"'))
        except ValueError:
            logger.error(f"Invalid call_sid: {self.call_sid}. Cannot convert to integer.")
            return "Error: call_sid inválido"

        current_dir = Path(__file__).resolve().parent
        parent_dir = current_dir.parent
        wav_path = os.path.join(parent_dir, "services", "functions", "implementations", "files", "transferir.wav")

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
                
                duration = self.calculate_wav_duration_from_base64(audio_base64)

                # Primera solicitud para reproducir el audio
                logger.warning(f"Enviando solicitud para reproducir el audio antes de transferir - {self.gettime()} - call_sid {self.call_sid}")
                response = await client.post("https://websockets.ccc.uno/api/v1/autoagent", json=payload, headers=headers)
                logger.debug(f"Playback response status: {response.status_code}")
                logger.debug(f"Response body: {response.text}")

                await asyncio.sleep(duration) 

                # Segunda solicitud para realizar la transferencia
                transfer_payload = {"call_id": call_id, "action": "transfer_agent"}
                logger.warning(f"Enviando solicitud para transferir la llamada - {self.gettime()} - call_sid {self.call_sid}")
                response = await client.post("https://websockets.ccc.uno/api/v1/autoagent", json=transfer_payload, headers=headers)
                logger.debug(f"Transfer response status: {response.status_code}")
                logger.debug(f"Transfer response body: {response.text}") 

            return "Se inició la transferencia al agente humano de manera exitosa."

        except Exception as e:
            error_traceback = traceback.format_exc()  # Obtiene el traceback completo como string
            formatted_traceback = error_traceback.replace("\n", " | ")
            logger.warning(f"Error en la función de transferencia: {str(e)}| Traceback: {formatted_traceback} - {self.gettime()} - call_sid {self.call_sid}")
            return f"Error al intentar transferir la llamada: {str(e)}"

    async def hangup_function(self):
        if not self.call_sid:
            logger.error("actions_call called without call_sid")
            return "Error: No se proporcionó call_sid"
        
        try:
            call_id = int(self.call_sid)
        except ValueError:
            logger.error(f"Invalid call_sid: {self.call_sid}. Cannot convert to integer.")
            return "Error: call_sid inválido"

        current_dir = Path(__file__).resolve().parent
        parent_dir = current_dir.parent
        wav_path = os.path.join(parent_dir, "services", "functions", "implementations", "files", "colgar.wav")

        # Leer archivo WAV de manera asíncrona
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
            
            duration = self.calculate_wav_duration_from_base64(audio_base64)
            
            # Primera solicitud para reproducir el audio
            logger.warning(f"Enviando primera solicitud para reproducir el audio de colgar - {self.gettime()} - call_sid {self.call_sid}")
            response = await client.post("https://websockets.ccc.uno/api/v1/autoagent", json=payload, headers=headers)
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response body: {response.text}")

            await asyncio.sleep(duration)

            # Segunda solicitud para colgar la llamada
            hangup_payload = {"call_id": call_id, "action": "hangup"}
            logger.warning(f"Enviando segunda solicitud para colgar la llamada - {self.gettime()} - call_sid {self.call_sid}")
            response = await client.post("https://websockets.ccc.uno/api/v1/autoagent", json=hangup_payload, headers=headers)
            logger.debug(f"Hangup response status: {response.status_code}")
            logger.debug(f"Hangup response body: {response.text}")

        return "Se colgó la llamada de manera exitosa."
    async def process_queue(self):
        while True:  
            call_id, action, data,text = await self.queue.get()
            self.switch = "playing"
            duration = await self._execute_action(call_id, action, data,text)
            if duration:
                logger.warning(f"esperando sleep duracion:{duration} text:{text} - {self.gettime()} - call_sid {self.call_sid}")
                await asyncio.sleep(duration)  # Espera la duración del audio antes de reanudar la escucha
            
            self.switch = "listening"
            
            if text is not None and isinstance(text, str) and text.strip():  # Verifica que text sea una cadena y no esté vacío
                text_lower = self.clean_text(text)  # Convierte el texto a minúsculas solo si es válido 
                logger.warning(f"Entra a la comparación de palabras para transferir o colgar - {text_lower} - {self.gettime()} - call_sid {self.call_sid}")
                self.para_colgar = [self.clean_text(phrase) for phrase in self.para_colgar]
                self.para_transferir = [self.clean_text(phrase) for phrase in self.para_transferir]
                for phrase in self.para_colgar:
                    logger.warning(f"Buscando '{phrase}' en '{text_lower}' colgar")
                    if phrase in text_lower:
                        # self.log("Detected word to hang up the call")
                        logger.warning(f"Detected word to hang up the call - {self.gettime()} - call_sid {self.call_sid}") 
                        if self.orchestrator:
                            self.orchestrator.logScript(f"Claro!, muchas gracias por tu tiempo -- COLGAR -- call_sid={self.call_sid}")
                        await self.hangup_function()
                    else:
                        logger.warning(f"Frase '{phrase}' NO encontrada en '{text_lower}'") 
                for phrase in self.para_transferir:
                    logger.warning(f"Buscando '{phrase}' en '{text_lower}' transferir")
                    if phrase in text_lower: 
                        # self.log("Detected word to transfer the call")
                        logger.warning(f"Detected word to transfer the call - {self.gettime()} - call_sid {self.call_sid}")
                        if self.orchestrator:
                            self.orchestrator.logScript(f"Claro!, lo transfiero con uno de mis compañeros -- TRANSFERIR -- call_sid={self.call_sid}")
                        await self.transfer_function()  
                    else:
                        logger.warning(f"Frase '{phrase}' NO encontrada en '{text_lower}'") 
            self.queue.task_done()

    async def actions_call(self, call_id: str, action: str, data: bytes = None,text:str=None):
        """Agrega la acción a la cola para su ejecución asincrónica."""
        await self.queue.put((call_id, action, data,text))
    async def initial_greet(self):
        """
        Envía un saludo inicial en la llamada especificada por `call_id`.

        :return: JSON con la confirmación de la reproducción del saludo.
        """
        wav_file_name = "hola_que_tal.wav"

        # Ruta al archivo WAV
        current_dir = Path(__file__).resolve().parent
        parent_dir = current_dir.parent
        wav_path = os.path.join(parent_dir, "services", "functions", "implementations", "files", wav_file_name)
        call_id=self.call_sid
        try:
            # Leer el archivo WAV de manera asíncrona
            wav_data = await asyncio.to_thread(lambda: open(wav_path, "rb").read())

            # Convertir a Base64 en un hilo separado
            audio_base64 = await asyncio.to_thread(base64.b64encode, wav_data)
            audio_base64 = audio_base64.decode("utf-8")

            # Crear el payload
            payload = {
                "call_id": int(call_id),
                "action": "playback",
                "data": {"audio_base64": audio_base64}
            }

            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "Content-Type": "application/json"}
                logger.warning(f"post playback initial greet - {self.gettime()} - call_sid {self.call_sid}")
                # Enviar la solicitud de manera asíncrona
                response = await client.post("https://websockets.ccc.uno/api/v1/autoagent", json=payload, headers=headers)
                logger.debug(f"Response status: {response.status_code}")
                logger.debug(f"Response body: {response.text}")

            return response.json()

        except Exception as e:
            logger.error(f"Error en initial_greet: {str(e)}")
            error_traceback = traceback.format_exc()  # Obtiene el traceback completo como string
            formatted_traceback = error_traceback.replace("\n", " | ")
            logger.warning(f"Error en initial_greet: {str(e)}| Traceback: {formatted_traceback} - {self.gettime()} - call_sid {self.call_sid}")
            return {"error": str(e)}
        
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
            # Calcular duración
            duration = n_frames / float(frame_rate)
            # adjusted_duration = max(duration - 0.5, 0)
            adjusted_duration = max( duration + 0.5, 0)

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
            n_frames = wav_file.getnframes()

            # Leer los datos PCM (sin encabezado WAV)
            pcm_bytes = wav_file.readframes(n_frames)

        return pcm_bytes
    async def _execute_action(self, call_id: str, action: str, data: bytes = None,text:str=None):
        logger.warning(f"inicia post playback text:{text} - {self.gettime()} - call_sid {self.call_sid}")
        payload=None
        duration=None
        if data:
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
        headers = {"accept": "application/json","Content-Type": "application/json"}  # Encabezados
        if data:
            logger.warning(f"obtiene duración post playback text:{text} - {self.gettime()} - call_sid {self.call_sid}")
            duration = await asyncio.to_thread(self.calculate_wav_duration_from_base64, data)
 
        async with httpx.AsyncClient() as client:
            try:
                logger.warning(f"post playback text:{text} duration: {duration} - {self.gettime()} - call_sid {self.call_sid}")
                response = await client.post(
                    "https://websockets.ccc.uno/api/v1/autoagent",
                    json=payload,
                    headers=headers,
                )
                logger.warning(f"post playback response {response.status_code} {response.text} - {self.gettime()} - call_sid {self.call_sid}")
            except httpx.RequestError as e:
                logger.error(f"Error en la solicitud HTTP: {e}")
                logger.warning(f"post playback error {e} - {self.gettime()} - call_sid {self.call_sid}")
                return None

        return duration
        
    
    async def connect(self):
        await self.websocket.accept()
        #debug
        #logger.debug("Customer call connected processing audio channel")
        client_ip = self.websocket.client.host
        # client_port = self.websocket.client.port
        identificador=id(self.websocket)
        logger.warning(f"Cliente conectado desde {client_ip} identificador {identificador}")
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
                    error_traceback = traceback.format_exc()  # Obtiene el traceback completo como string
                    formatted_traceback = error_traceback.replace("\n", " | ")
                    logger.warning(f"Error procesando el flujo de audio: {str(e)}| Traceback: {formatted_traceback} - {self.gettime()} - call_sid {self.call_sid}")
                    raise e
            logger.warning(f"Getting conversation for analysis - {self.gettime()} - call_sid {self.call_sid}")
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
                    * STC-140: Si el cliente contesta, confirma identidad, y puede pagar antes de la fecha límite, no se transiere al agente con exito.
                    * STC-145: Si el cliente contesta, confirma identidad, no puede pagar antes de la fecha límite, y es transferido a un agente con exito.
                    
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
            # logger.warning(f"messages: {messages}")
            try:
                # Llamar al modelo para obtener la respuesta
                logger.warning(f"Send to bot for checkpoints - {self.gettime()} - call_sid {self.call_sid}")
                respuesta = await llm.chat.completions.create(
                    model="gpt-3.5-turbo-1106",
                    temperature=0.1,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                # Extraer checkpoints de la respuesta
                logger.warning(f"Extraer checkpoints de la respuesta {respuesta.choices[0].message.content} - {self.gettime()} - call_sid {self.call_sid}")
             
                checkpoints = json.loads(respuesta.choices[0].message.content).get("checkpoints", [])
                collected_checkpoints.extend(checkpoints)  # Acumular checkpoints generados
            except Exception as e:
                error_traceback = traceback.format_exc()  # Obtiene el traceback completo como string
                formatted_traceback = error_traceback.replace("\n", " | ")
                logger.warning(f"Error al procesar la respuesta del modelo: {str(e)}| Traceback: {formatted_traceback} - {self.gettime()} - call_sid {self.call_sid}")
                return
        except Exception as e:
            logger.error(f"Error general en process_stream: {e}")
            error_traceback = traceback.format_exc()  # Obtiene el traceback completo como string
            formatted_traceback = error_traceback.replace("\n", " | ")
            logger.warning(f"Error general en process_stream: {str(e)}| Traceback: {formatted_traceback} - {self.gettime()} - call_sid {self.call_sid}")
            raise e
        if self.orchestrator:
            logger.warning(f"Códigos de estado: {json.dumps(collected_checkpoints)}")
            self.orchestrator.log(f"Códigos de estado: {json.dumps(collected_checkpoints)}")
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
                logger.warning(f"Enviando a layer7 estado {checkpoint} con dnid {dnid} - {self.gettime()} - call_sid {self.call_sid}")
                self.orchestrator.log(f"Enviando a layer7 estado {checkpoint} con dnid {dnid}")
                if response.status == 200:
                    logger.debug("Checkpoints sent successfully.")
                else:
                    logger.error(f"Error en la solicitud HTTP. Status: {response.status}")
            except Exception as e:
                error_traceback = traceback.format_exc()  # Obtiene el traceback completo como string
                formatted_traceback = error_traceback.replace("\n", " | ")
                logger.warning(f"Error al enviar datos al servidor: {str(e)}| Traceback: {formatted_traceback} - {self.gettime()} - call_sid {self.call_sid}")
            
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
                error_traceback = traceback.format_exc()  # Obtiene el traceback completo como string
                formatted_traceback = error_traceback.replace("\n", " | ")
                logger.warning(f"Error asegurando lista: {str(e)}| Traceback: {formatted_traceback} - {self.gettime()} - call_sid {self.call_sid}")
                return []

        # Asegurar que ambos datos sean listas válidas
        customer_list = ensure_list(customer_data)
        bot_list = ensure_list(bot_data)

        return customer_list + bot_list


    async def handle_event(self, data):
        if 'text' in data:
            datos = data["text"].strip('"').strip()
            if re.match(self.pattern, datos):
                self.switch="not_listening"
                self.stream_sid, self.call_sid, self.number = datos.split('#')
                logger.warning(f"Codigo: {self.stream_sid}, Call ID: {self.call_sid}, Number: {self.number} - {self.gettime()} - call_sid {self.call_sid}")
                dnid=f"{self.stream_sid}%23{self.call_sid}%23{self.number}"
                # logger.debug(dnid)
                context=await self.get_lead(dnid=dnid)
                logger.warning(f"context: {context}")
                self.initial_data=context
        elif 'bytes' in data:
            datos= data["bytes"]
            return await self.process_media_event(datos)

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
     
            raw_audio_data = audio_payload
            # umbral = self.calcular_umbral(audio_payload)
            # rms = audioop.rms(audio_payload, 2)  # Calculate RMS
            rms = await asyncio.to_thread(audioop.rms, data, 2)
            # if rms > 200 and self.switch == "listening":
            if rms > 200 and self.switch == "listening":
                self.playsequence.append(raw_audio_data)
                self.silence_duration = 0
                return raw_audio_data
            else:
                self.silence_duration += self.duration
                if self.silence_duration >= 45.0:
                    self.silence_duration = 0
                    logger.warning("Más de 45 segundos de silencio detectados.")
                    await self.actions_call(self.call_sid, "hangup")

                # Generate silence if below threshold or not in listening state
                raw_audio_data = await self.generate_silence()
                return raw_audio_data
        except (binascii.Error, ValueError) as e:
            # Handle invalid Base64 or decoding errors 
            logger.error(f"Error decoding Base64: {e}")
            return await self.generate_silence()

    async def generate_silence(self, duration=0.02, sample_width=2, sample_rate=8000):
        """Genera un chunk de audio en silencio en formato µ-law."""
        num_samples = int(duration * sample_rate)
        silence_data = b"\x00" * (num_samples * sample_width)
        
        ulaw_silence = await asyncio.to_thread(audioop.lin2ulaw, silence_data, sample_width)

        if not isinstance(ulaw_silence, bytes):  # 🔥 Verificar que sea bytes antes de regresar
            raise TypeError("generate_silence() debe devolver un objeto de tipo bytes")

        return ulaw_silence

    async def send_audio(self, audio_data,text:str=None):
        if self.is_connected:
            logger.warning(f"sending audio frame to customer - {self.gettime()} - call_sid {self.call_sid}")
            byte_data = self.base64_wav_to_pcm(audio_data)
            self.playsequence.append(byte_data)
            self.silence_duration = 0
            await self.actions_call(self.call_sid,"playback",audio_data,text)
            self.silence_duration = 0
          
        else:
            logger.debug("User is not connected anymore skipping audio sending to customer")

    async def send_mark(self, mark):
        logger.debug("Sending {} mark to Twilio".format(mark))
        if self.is_connected:
            self.switch=mark
           
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