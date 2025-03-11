import requests
from pydub import AudioSegment
from io import BytesIO
import speech_recognition as sr
import os
import tempfile
import logging
import traceback

logger = logging.getLogger(__name__)

def download(url):
    try:
        logger.debug(f"Iniciando descarga desde: {url}")
        response = requests.get(url)
        if response.status_code == 200:
            logger.debug(f"Archivo descargado correctamente ({len(response.content)} bytes)")
            return BytesIO(response.content)
        else:
            raise Exception(f"Failed to download audio file: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Error en la descarga: {str(e)}")
        raise

def determine_audio_type(url):
    """Determine audio file type based on URL extension"""
    logger.debug(f"Determinando tipo de archivo a partir de URL: {url}")
    if url.lower().endswith('.mp3'):
        return 'mp3'
    elif url.lower().endswith('.ogg'):
        return 'ogg'
    else:
        logger.warning(f"No se pudo determinar el tipo de archivo por la extensión, usando mp3 por defecto: {url}")
        return 'mp3'

def transcribe_audio_to_text(audio_bytes, file_type, language):
    temp_path = None
    wav_path = None
    
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_type}') as temp_file:
            temp_path = temp_file.name
            # Asegurarse de que audio_bytes sea un BytesIO
            if isinstance(audio_bytes, BytesIO):
                content = audio_bytes.getvalue()
            else:
                content = audio_bytes
            temp_file.write(content)
        
        logger.debug(f"Archivo temporal creado en {temp_path}")
        
        # Load the audio with pydub
        try:
            if file_type == 'mp3':
                logger.debug("Cargando archivo MP3 con pydub")
                audio = AudioSegment.from_mp3(temp_path)
            elif file_type == 'ogg':
                logger.debug("Cargando archivo OGG con pydub")
                audio = AudioSegment.from_ogg(temp_path)
            else:
                raise ValueError(f"Unsupported audio format: {file_type}")
        except Exception as e:
            logger.error(f"Error al cargar el audio con pydub: {e}")
            # Intentar usando ffmpeg directamente
            logger.debug("Intentando usar ffmpeg directamente")
            audio = AudioSegment.from_file(temp_path, format=file_type)
        
        # Export to WAV for speech recognition
        wav_path = temp_path + '.wav'
        logger.debug(f"Exportando a WAV: {wav_path}")
        audio.export(wav_path, format="wav")
        
        # Perform speech recognition
        logger.debug(f"Iniciando reconocimiento de voz con idioma: {language}")
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            logger.debug("Grabando audio de archivo")
            audio_data = recognizer.record(source)
            logger.debug("Enviando a Google Speech Recognition")
            text = recognizer.recognize_google(audio_data, language=language)
            logger.debug(f"Texto reconocido: {text[:50]}...")
        
        # Clean up temporary files
        try:
            os.unlink(temp_path)
            os.unlink(wav_path)
            logger.debug("Archivos temporales eliminados")
        except Exception as e:
            logger.warning(f"No se pudieron eliminar archivos temporales: {e}")
        
        return text
    
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {str(e)}")
        logger.error(traceback.format_exc())
        # Clean up
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        if wav_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except:
                pass
        raise

def TranscribeOGG(url, language):
    try:
        logger.debug(f"Iniciando transcripción de audio desde: {url} con idioma: {language}")
        audio_bytes = download(url)
        file_type = determine_audio_type(url)
        logger.debug(f"Procesando archivo de audio de tipo: {file_type}")
        result = transcribe_audio_to_text(audio_bytes, file_type, language)
        logger.debug(f"Transcripción completada: {result[:50]}...")
        return result
    except sr.UnknownValueError:
        logger.warning("Google Speech Recognition no pudo entender el audio")
        return "Lo siento, no pude entender el audio."
    except sr.RequestError as e:
        logger.error(f"Error en la API de Google Speech: {str(e)}")
        return "Lo siento, hubo un problema con el servicio de reconocimiento de voz."
    except Exception as e:
        logger.error(f"Error procesando audio: {str(e)}")
        logger.error(traceback.format_exc())
        return f"Lo siento, ocurrió un error al procesar el audio: {str(e)}"