# In websocket_handlers.py
import asyncio
import json

import aiohttp
from src.utils import logger
from fastapi import WebSocket
from amazon_transcribe.client import TranscribeStreamingClient
from src.openai_chat import ChatMemory
from src.text_to_speech import OpenAITextToSpeechService, TextToSpeechService
from src.transcription import SttEventHandler
from src.websocket_handlers.stream_handler import stream
from src.tools.identify import get_customer_identity
import openai


async def write_chunks(ws_stream, stt_stream):
    async for chunk in ws_stream:
        await stt_stream.input_stream.send_audio_event(audio_chunk=chunk)
    await stt_stream.input_stream.end_stream()


async def websocket_endpoint(
    ws: WebSocket, tts_service: TextToSpeechService, system_message, hello_message
):
    await ws.accept()

    stream_sid = None
    call_sid = None
    async for stream_sid, call_sid in stream(ws):
        break
    
    
   

    customer_data = await get_customer_identity(call_sid)
    retry = customer_data["retry"]
    print("ACAAaaaaaaaaaaaaaaaaaaaaa----------->",retry)
    dealer = customer_data["dealer"]    
    customer_name = customer_data["nombre"]
    codigo_seguridad = customer_data["ps"]
    contacto = customer_data["contacto1"]
    contacto2 = customer_data["contacto2"]
    contacto3 = customer_data["contacto3"]
    hello = hello_message.format(
        customer_name=customer_name,
        dealer=dealer,
        contacto=contacto,
        contacto2=contacto2,
        contacto3=contacto3,
    )
    Calle = customer_data["calle"]
    Localidad = customer_data["localidad"]
    Provincia = customer_data["provincia"]
    contacto = customer_data["contacto1"]
    contacto2 = customer_data["contacto2"]
    contacto3 = customer_data["contacto3"]
    clave1 = customer_data["ps1"]
    clave2 = customer_data["ps2"]
    clave3 = customer_data["ps3"]
    dealer = customer_data["dealer"]
    system = system_message.format(
        customer_data=json.dumps(customer_data, indent=2),
        dealer=dealer,
        call_sid=call_sid,
        customer_name=customer_name,
        codigo_seguridad=json.dumps(customer_data, indent=2),
        Calle=Calle,
        Localidad=Localidad,
        Provincia=Provincia,
        contacto=contacto,
        contacto2=contacto2,
        contacto3=contacto3,
        clave1=clave1,
        clave2=clave2,
        clave3=clave3,
        retry=retry
    )
    print(system)
    await ws.send_json(
        {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": "stop"},
        }
    )

    await tts_service.synthesize_speech(hello, stream_sid, ws)

    await ws.send_json(
        {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": "talk"},
        }
    )

    stt_client = TranscribeStreamingClient(region="us-west-2")
    stt_stream = await stt_client.start_stream_transcription(
        language_code="es-US",
        media_sample_rate_hz=8000,
        media_encoding="pcm",
        enable_partial_results_stabilization=False,
    )

    chat_memory = ChatMemory()
    chat_memory.add_message("system", system)
    chat_memory.add_message("assistant", hello)

    handler = SttEventHandler(
        stt_stream.output_stream, ws, stream_sid, chat_memory, tts_service
    )
    try:
        await asyncio.gather(
            write_chunks(stream(ws), stt_stream),
            handler.handle_events(),
        )
    except Exception as e:
        llm = openai.AsyncClient()
        messages = [
            {
                "role": "system",
                "content": """Analiza la conversacion y devuelve un json con base a lo contestado por el cliente. 
                En caso de no haberla requerido, devuelve un false.

                APERTURA
                * APERTURA-NOC-SI: Si el cliente solicita ayuda cuando le informamos que no recibimos ningun evento de apertura.
                * APERTURA-NOC-NO: Si el cliente NO SOLICITA ayuda cuando le informamos que no recibimos ningun evento de apertura.
                * APERTURA-SISTEMA-ARMADO-SI: Si el cliente responde haber armado su sistema, y desea recibir ayuda.
                * APERTURA-SISTEMA-ARMADO-NO: Si el cliente responde haber armado su sistema, Y NO DESEA recibir ayuda.
                * APERTURA-COLGO: Si el cliente cuelga durante la ejecución en event_not_yet_open.
                CIERRE
                * CIERRE-NCL-SI: Si el cliente solicita ayuda cuando le informamos que no recibimos ningun evento de cierre.
                * CIERRE-NCL-NO: Si el cliente NO SOLICITA ayuda cuando le informamos que no recibimos ningun evento de cierre.
                * CIERRE-SISTEMA-ARMADO-SI: Si el cliente responde haber armado su sistema, y desea recibir ayuda.
                * CIERRE-SISTEMA-ARMADO-NO: Si el cliente responde haber armado su sistema, Y NO DESEA recibir ayuda.
                * CIERRE-COLGO: Si el cliente cuelga durante la ejecución en event_not_yet_closed.
                GENERAL
                * COLGO: Si el cliente termina la llamada, antes de llegar al FINAL del flujo.

                Ejemplo
                
                {{
                    "tipo": NOC-SI
                }}
                
                """,
            },
            {
                "role": "user",
                "content": json.dumps(chat_memory.get_messages(), indent=2),
            },
        ]
        response = await llm.chat.completions.create(
            model="gpt-4-0125-preview",
            temperature=0.1,
            messages=messages,
            response_format={"type": "json_object"},
        )
        response = json.loads(response.choices[0].message.content)["tipo"]

        url = "https://servweb.we-monitor.com/kpis/api/values/1/EVENTOS"
        headers = {
            "Accept": "/",
            "User-Agent": "Beholder",
            "Content-Type": "application/json",
        }

        payload = json.dumps(
            {
                "idcuenta": customer_data["idcuenta"],
                "clavedealer": customer_data["clavedealer"],
                "eventomanual": response,
                "idevento": customer_data.get("idevento"),
                "contacto1": customer_data["contacto1"],
                "telefono1": customer_data["telefono1"],
                "status1": customer_data.get("status1"),
                "contacto2": customer_data["contacto2"],
                "telefono2": customer_data["telefono2"],
                "status2": customer_data.get("status2"),
                "contacto3": customer_data["contacto3"],
                "telefono3": customer_data["telefono3"],
                "status3": customer_data.get("status3"),
                "contesto_contacto": retry

            }
        )
        print("PAYLOAD QUE ENVIO",payload)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, headers=headers) as response:
                result = await response.text()
                print(result)