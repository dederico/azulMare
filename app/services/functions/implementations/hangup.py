from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import os

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")


# Initialize the Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


async def hangup(call_sid):
    """Terminar interaccion si el usuario asi lo solicita.

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.

    Returns:
        string: Mensaje de confirmacion.
    """

    response = VoiceResponse()
    response.say("Thanks for your time.", voice="Polly.Salli-Neural", language="en-US")
    response.pause(length=5)
    client.calls(call_sid).update(twiml=response.to_xml())
    client.calls(call_sid).update(status="completed")
    return "The interaction is finished."