import requests
from pydub import AudioSegment
from io import BytesIO
import speech_recognition as sr
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

def download(url):
    response = requests.get(url)
    if response.status_code == 200:
        print("File Downloaded successfully")
        return BytesIO(response.content)
    else:
        raise Exception(f"Failed to download audio file: {response.status_code}")

def determine_audio_type(url):
    """Determine audio file type based on URL extension"""
    if url.lower().endswith('.mp3'):
        return 'mp3'
    elif url.lower().endswith('.ogg'):
        return 'ogg'
    else:
        # Default to mp3 for Chat2Desk (based on your payload example)
        return 'mp3'

def transcribe_audio_to_text(audio_bytes, file_type, language):
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_type}') as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio_bytes.getvalue())
        
        # Load the audio with pydub
        if file_type == 'mp3':
            audio = AudioSegment.from_mp3(temp_path)
        elif file_type == 'ogg':
            audio = AudioSegment.from_ogg(temp_path)
        else:
            raise ValueError(f"Unsupported audio format: {file_type}")
        
        # Export to WAV for speech recognition
        wav_path = temp_path + '.wav'
        audio.export(wav_path, format="wav")
        
        # Perform speech recognition
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language=language)
        
        # Clean up temporary files
        os.unlink(temp_path)
        os.unlink(wav_path)
        
        return text
    
    except Exception as e:
        logger.error(f"Error transcribing audio: {str(e)}")
        if 'temp_path' in locals():
            try:
                os.unlink(temp_path)
            except:
                pass
        if 'wav_path' in locals():
            try:
                os.unlink(wav_path)
            except:
                pass
        raise

def TranscribeOGG(url, language):
    try:
        audio_bytes = download(url)
        file_type = determine_audio_type(url)
        logger.debug(f"Processing audio file of type: {file_type}")
        return transcribe_audio_to_text(audio_bytes, file_type, language)
    except sr.UnknownValueError:
        logger.warning("Google Speech Recognition could not understand audio")
        return "Lo siento, no pude entender el audio."
    except sr.RequestError as e:
        logger.error(f"Google Speech API error: {str(e)}")
        return "Lo siento, hubo un problema con el servicio de reconocimiento de voz."
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        return f"Lo siento, ocurrió un error al procesar el audio: {str(e)}"