import audioop
import base64
from typing import AsyncGenerator
import aiobotocore
from aiobotocore.session import AioSession
import time
from app.models.Config import Config
from app.util.database import LocalStorage
from app.services.tts.tts_service import TTSService
import wave
import tempfile
# Configuration constants
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2
CHANNELS = 1
AWS_REGION = "us-west-2"


class AmazonTTSService(TTSService):
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region_name: str,
        stream_results: bool = False,
        language: str = None
    ):
        self.client = None
        self.stream_results = stream_results
        self.access_key = access_key
        self.secret_key = secret_key
        self.region_name = region_name
        self.lang = language

    async def initialize_client(self):
        session = AioSession()
        session.set_credentials(
            access_key=self.access_key,
            secret_key=self.secret_key,
        )
        self.client = await session._create_client(
            service_name="polly",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name,
        )
        self.client = await self.client.__aenter__()

    async def synthesize(self, text: str):
        """
        Synthesizes speech using Amazon Polly and sends it over WebSocket.

        :param text: Text to be converted to speech.
        """
        if not self.client:
            await self.initialize_client()

        if self.client:
            synth = await self.client.synthesize_speech(
                Text=text,
                TextType="ssml" if "<speak>" in text else "text",
                OutputFormat="pcm",
                VoiceId="Lupe",
                SampleRate=str(SAMPLE_RATE),
                Engine="neural",
                LanguageCode=self.lang,
            )  # type: ignore
            
            # wav_buffer = io.BytesIO()
            # with wave.open(wav_buffer, 'wb') as wf:
            #     wf.setnchannels(1)  # Mono audio
            #     wf.setsampwidth(2)  # 2 bytes por muestra (16 bits)
            #     wf.setframerate(int(SAMPLE_RATE))  # Frecuencia de muestreo
            #     wf.writeframes(pcm_audio)
            
            # wav_buffer.seek(0)
            # wav_data = wav_buffer.read()

            # base64_audio = base64.b64encode(wav_data).decode("utf-8")
            # return base64_audio
            pcm_audio = await synth["AudioStream"].read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file_name = temp_file.name  # Obtener el nombre del archivo
                with wave.open(temp_file, 'wb') as wf:
                    wf.setnchannels(1)  # Mono audio
                    wf.setsampwidth(2)  # 2 bytes por muestra (16 bits)
                    wf.setframerate(int(SAMPLE_RATE))  # Frecuencia de muestreo
                    wf.writeframes(pcm_audio)
            with open(temp_file_name, "rb") as f:
                wav_data = f.read()
                base64_audio = base64.b64encode(wav_data).decode("utf-8")
            return base64_audio
            # audio = audioop.lin2ulaw(mulaw_audio, SAMPLE_WIDTH)
            # audio = audioop.ulaw2lin(mulaw_audio, SAMPLE_WIDTH)

            # return base64_audio

        # except Exception as e:
        #     print(f"Error in AmazonTTS: {e}")

    async def stream_synthesize(self, text: str) -> AsyncGenerator[str, None]:
        yield ""
        raise NotImplementedError