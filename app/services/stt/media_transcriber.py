import requests
from pydub import AudioSegment
from io import BytesIO
import speech_recognition as sr

def download(url):
    response = requests.get(url)
    if response.status_code == 200:
        print("File Downloaded successfully")
        return BytesIO(response.content)
    else:
        raise Exception(f"Failed to download audio file: {response.status_code}")

def transcribe_ogg_to_text(ogg_audio_bytes, language):
    audio = AudioSegment.from_ogg(ogg_audio_bytes)

    with BytesIO() as wav_file:
        audio.export(wav_file, format="wav")
        wav_file.seek(0)

        recognizer = sr.Recognizer()
        
        try:
            with sr.AudioFile(wav_file) as source:
                audio_data = recognizer.record(source)
                return recognizer.recognize_google(audio_data, language=language)
        except sr.UnknownValueError:
            return False
        except sr.RequestError:
            return False

def TranscribeOGG(url, language):
    audio = download(url)
    return transcribe_ogg_to_text(audio, language)
