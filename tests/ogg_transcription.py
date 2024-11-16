import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.stt.media_transcriber import TranscribeOGG

url = "https://api.twilio.com/2010-04-01/Accounts/AC274ae17c4a1dc4f8d1097d5b7f03aef3/Messages/MMa46e8a96f2163cdc13f16527c00a3b0c/Media/ME2a43e3a225d91c4db4b29126082d4d37"
print("OUTPUT:", TranscribeOGG(url, "es-US"))