import json
import base64
import io
import wave
import pyaudio # For pyaudio.paContinue
import websocket # For WebSocketConnectionClosedException type hint

from . import config_new as config
from . import globals_new as app_globals

def _create_wav_in_memory(pcm_data: bytes, rate: int, channels: int, sample_width: int) -> bytes:
    """Convert raw PCM data to WAV format in memory"""
    with io.BytesIO() as wav_file_stream:
        with wave.open(wav_file_stream, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)
        return wav_file_stream.getvalue()

def transcribe_with_scribe(audio_data: bytes) -> str:
    """Transcribe audio using ElevenLabs Scribe"""
    if not config.elevenlabs_client:
        print("⚠️ [SCRIBE] ElevenLabs client not initialized. Skipping transcription.")
        return "[Scribe Error: Client not initialized]"
    if not audio_data:
        return ""

    try:
        # Ensure audio_data is in WAV format
        if not audio_data.startswith(b'RIFF'):
            # Raw PCM data needs to be converted to WAV
            wav_audio_data = _create_wav_in_memory(
                pcm_data=audio_data,
                rate=config.PYAUDIO_RATE,
                channels=config.PYAUDIO_CHANNELS,
                sample_width=config.PYAUDIO_SAMPLE_WIDTH
            )
        else:
            # Already WAV format
            wav_audio_data = audio_data
            
        response = config.elevenlabs_client.speech_to_text.convert(
            file=wav_audio_data,
            model_id=config.ELEVENLABS_SCRIBE_MODEL_ID,
            tag_audio_events=False
        )

        # Process the response based on ElevenLabs API structure
        if hasattr(response, 'text') and isinstance(response.text, str):
            return response.text
        elif isinstance(response, str):
            return response
        else:
            try:
                # Try to serialize the response for debugging
                response_repr = str(response)
                if hasattr(response, 'model_dump_json'):
                    response_repr = response.model_dump_json()
                elif hasattr(response, '__dict__'):
                    response_repr = str(response.__dict__)
                print(f"⚠️ [SCRIBE] Unexpected response structure: {response_repr}")
            except:
                pass
            return f"[Scribe Error: Unexpected response structure]"

    except Exception as e:
        print(f"⚠️ [SCRIBE] Error during transcription: {e} (Type: {type(e).__name__})")
        return f"[Scribe Error: {type(e).__name__} - {str(e)}]"

def pyaudio_callback_new(in_data, frame_count, time_info, status):
    """Callback for PyAudio to process incoming audio data"""
    if app_globals.audio_capture_active.is_set():
        with app_globals.audio_buffer_lock:
            app_globals.full_audio_data.extend(in_data)

        # Send to WebSocket if connected
        if app_globals.ws_app and app_globals.ws_app.sock and app_globals.ws_app.sock.connected:
            try:
                app_globals.ws_app.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(in_data).decode("utf-8")
                }))
            except websocket.WebSocketConnectionClosedException:
                pass  # Expected if connection closes mid-send
            except Exception as e:
                pass  # Avoid spamming logs for minor send errors

    return (None, pyaudio.paContinue)
