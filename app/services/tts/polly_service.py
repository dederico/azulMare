import audioop
import base64
from typing import AsyncGenerator
import aiobotocore
from aiobotocore.session import AioSession
import time
from app.models.Config import Config
from app.util.database import LocalStorage
from app.services.tts.tts_service import TTSService

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
    ):
        self.client = None
        self.stream_results = stream_results
        self.access_key = access_key
        self.secret_key = secret_key
        self.region_name = region_name

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

        ls = LocalStorage()
        config = { c.name: c.value for c in ls.GetAll(Config) }
        lang = config.get("Lang") or "es-US"

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
                LanguageCode=lang,
            )  # type: ignore
            mulaw_audio = await synth["AudioStream"].read()
            audio = audioop.lin2ulaw(mulaw_audio, SAMPLE_WIDTH)
            base64_audio = base64.b64encode(audio).decode("utf-8")

            return base64_audio

        # except Exception as e:
        #     print(f"Error in AmazonTTS: {e}")

    async def stream_synthesize(self, text: str) -> AsyncGenerator[str, None]:
        yield ""
        raise NotImplementedError