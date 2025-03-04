import audioop
import base64
from typing import AsyncGenerator
import aiobotocore
from aiobotocore.session import AioSession
import wave
import io

# Configuración de Polly
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2
CHANNELS = 1
AWS_REGION = "us-west-2"


class AmazonTTSService:
    def __init__(self, access_key: str, secret_key: str, region_name: str, stream_results: bool = False, language: str = None):
        self.client = None
        self.stream_results = stream_results
        self.access_key = access_key
        self.secret_key = secret_key
        self.region_name = region_name
        self.lang = language

    async def initialize_client(self):
        """Inicializa el cliente de Amazon Polly"""
        session = AioSession()
        self.client = await session.create_client(
            service_name="polly",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name,
        ).__aenter__()

    async def close_client(self):
        """Cierra el cliente Polly para liberar memoria"""
        if self.client:
            await self.client.__aexit__(None, None, None)
            self.client = None

    async def synthesize(self, text: str):
        """Convierte texto en audio usando Amazon Polly y devuelve base64"""
        if not self.client:
            await self.initialize_client()

        try:
            response = await self.client.synthesize_speech(
                Text=text,
                TextType="ssml" if "<speak>" in text else "text",
                OutputFormat="pcm",
                VoiceId="Lupe",
                SampleRate=str(SAMPLE_RATE),
                Engine="neural",
                LanguageCode=self.lang,
            )

            pcm_audio = await response["AudioStream"].read()

            # Convertir PCM a WAV
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(int(SAMPLE_RATE))
                wf.writeframes(pcm_audio)

            # Convertir WAV a Base64
            wav_buffer.seek(0)
            base64_audio = base64.b64encode(wav_buffer.read()).decode("utf-8")

            return base64_audio

        except Exception as e:
            print(f"Error en AmazonTTS: {e}")
            return None
        finally:
            await self.close_client()  # Cerrar cliente después de usar

    async def stream_synthesize(self, text: str) -> AsyncGenerator[str, None]:
        """Método placeholder para la síntesis en streaming"""
        yield "Streaming no implementado aún."
