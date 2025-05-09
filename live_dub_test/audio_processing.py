import io
import wave
import tempfile
import os
import base64
import json
import pyaudio # For pyaudio.paContinue
import websocket # For WebSocketConnectionClosedException type hint
import numpy as np # For audio data manipulation

from elevenlabs import VoiceSettings

from . import config
from . import globals

def generate_audio_elevenlabs_tts(text: str) -> bytes | None:
    if not config.elevenlabs_client:
        print("⚠️ [TTS_GEN_ELEVENLABS] ElevenLabs client not initialized. Skipping audio generation.")
        return None
    if not config.ELEVENLABS_VOICE_ID or config.ELEVENLABS_VOICE_ID == "YOUR_VOICE_ID":
        print("⚠️ [TTS_GEN_ELEVENLABS] ElevenLabs Voice ID not configured. Skipping audio generation.")
        return None
    if not text.strip():
        return None

    try:
        response_iterator = config.elevenlabs_client.text_to_speech.convert(
            voice_id=config.ELEVENLABS_VOICE_ID,
            output_format=config.ELEVENLABS_OUTPUT_FORMAT, # Now configured for PCM
            text=text,
            model_id=config.ELEVENLABS_MODEL_ID,
            optimize_streaming_latency=config.ELEVENLABS_OPTIMIZE_STREAMING_LATENCY, # Added latency optimization
            voice_settings=VoiceSettings(
                stability=1, # Stability and similarity might affect latency, adjust if needed
                similarity_boost=0.5,
                style=0,
                use_speaker_boost=True,
                speed=1.2
            ),
        )
        audio_bytes = b"".join([chunk for chunk in response_iterator if chunk])
        return audio_bytes
    except Exception as e:
        print(f"⚠️ [TTS_GEN_ELEVENLABS] Error generating audio with ElevenLabs SDK: {e}")
        return None

def generate_audio_tts(text: str) -> bytes | None:
    if config.TTS_PROVIDER == "AZURE":
        if not config.client_az_translation: # Assuming translation client is used for TTS deployment
            print("⚠️ [TTS_GEN_AZURE] Azure OpenAI client for TTS not initialized. Skipping audio generation.")
            return None
        if not text.strip():
            return None
        try:
            # For OpenAI client, response_format "pcm" gives 24kHz.
            # If we need 16kHz to match PyAudio_Rate, we might need to resample
            # or check if Azure specific SDK offers more control for OpenAI deployments.
            # For now, let's use "pcm" and Pygame mixer will handle resampling if its init freq is different.
            # However, it's best if TTS output matches mixer init freq.
            # If AZ_TTS_OUTPUT_FORMAT is "pcm", it defaults to 24kHz.
            # Let's assume for now the mixer will handle it or we adjust mixer to 24kHz if Azure is primary.
            # For consistency with ElevenLabs PCM output at PYAUDIO_RATE (16kHz),
            # it would be ideal if Azure could also output 16kHz PCM.
            # The "pcm" option for OpenAI API is 24kHz.
            # If using Azure Cognitive Services Speech SDK directly, more format control is available.
            # With current OpenAI library for Azure, "pcm" is the option for raw audio.
            azure_response_format = config.AZ_TTS_OUTPUT_FORMAT
            if azure_response_format == "pcm" and config.PYAUDIO_RATE != 24000:
                 print(f"⚠️ [TTS_GEN_AZURE] Requesting 'pcm' (24kHz) from Azure TTS, but PYAUDIO_RATE is {config.PYAUDIO_RATE}. Mixer will resample.")

            with config.client_az_translation.audio.speech.with_streaming_response.create(
                model=config.AZ_TTS_MODEL,
                voice=config.AZ_TTS_VOICE,
                input=text,
                response_format=azure_response_format # Added response_format
            ) as response:
                audio_bytes = response.read()
            return audio_bytes
        except Exception as e:
            print(f"⚠️ [TTS_GEN_AZURE] Error generating audio with Azure OpenAI TTS: {e}")
            return None
    elif config.TTS_PROVIDER == "ELEVENLABS":
        return generate_audio_elevenlabs_tts(text)
    else:
        print(f"⚠️ [TTS_GEN] Unknown TTS_PROVIDER: {config.TTS_PROVIDER}. Skipping audio generation.")
        return None

def play_audio_pygame(audio_bytes: bytes | None):
    if not audio_bytes:
        return
    try:
        if not globals.pygame.mixer.get_init():
            print("⚠️ [PLAYBACK] Pygame mixer not initialized. Cannot play audio.")
            return

        actual_freq, actual_format, actual_channels = globals.pygame.mixer.get_init()
        
        # Our source audio is configured by config.PYAUDIO_CHANNELS (expected to be 1 for mono)
        source_channels = config.PYAUDIO_CHANNELS

        processed_audio_bytes = audio_bytes

        if actual_channels == 2 and source_channels == 1:
            print(f"🔊 [PLAYBACK_CONVERT] Mixer is stereo ({actual_channels}ch), source audio is mono ({source_channels}ch). Converting mono to stereo.")
            # Assuming 16-bit PCM, so 2 bytes per sample
            if actual_format == -16: # Signed 16-bit
                # Convert mono PCM 16-bit to stereo PCM 16-bit by duplicating samples
                mono_samples = np.frombuffer(audio_bytes, dtype=np.int16)
                stereo_samples = np.repeat(mono_samples, 2) # Duplicates each sample: L, R, L, R...
                processed_audio_bytes = stereo_samples.tobytes()
            else:
                print(f"⚠️ [PLAYBACK_CONVERT] Mono to stereo conversion for format {actual_format} not implemented. Playing as is.")
        elif actual_channels == 1 and source_channels == 2:
            print(f"⚠️ [PLAYBACK_CONVERT] Mixer is mono ({actual_channels}ch), source audio is stereo ({source_channels}ch). This might not play correctly. Playing as is.")
        elif actual_channels != source_channels:
            print(f"⚠️ [PLAYBACK_CONVERT] Channel mismatch: Mixer {actual_channels}ch, Source {source_channels}ch. Format {actual_format}. Playing as is, may have issues.")

        # --- NEW: Ajuste de velocidade de reprodução ---
        if config.PLAYBACK_SPEED != 1.0:
            speed = config.PLAYBACK_SPEED
            samples = np.frombuffer(processed_audio_bytes, dtype=np.int16)
            if actual_channels > 1:
                samples = samples.reshape(-1, actual_channels)
                new_length = int(samples.shape[0] / speed)
                new_samples = []
                for ch in range(actual_channels):
                    channel_data = samples[:, ch]
                    new_indices = np.linspace(0, len(channel_data) - 1, new_length)
                    new_channel = np.interp(new_indices, np.arange(len(channel_data)), channel_data)
                    new_samples.append(new_channel)
                new_samples = np.stack(new_samples, axis=1).flatten().astype(np.int16)
            else:
                new_length = int(len(samples) / speed)
                new_indices = np.linspace(0, len(samples) - 1, new_length)
                new_samples = np.interp(new_indices, np.arange(len(samples)), samples).astype(np.int16)
            processed_audio_bytes = new_samples.tobytes()
        # --- Fim do ajuste de velocidade ---

        # Create a Sound object directly from the PCM audio_bytes
        # Assumes audio_bytes are raw PCM data matching the mixer's initialized format
        # (frequency, bits, channels - after potential conversion)
        sound = globals.pygame.mixer.Sound(buffer=processed_audio_bytes)
        channel = sound.play()

        if channel is not None:
            # Wait for the sound to finish playing on this channel
            while channel.get_busy():
                globals.pygame.time.Clock().tick(30) # Tick rate can be adjusted
        else:
            print("⚠️ [PLAYBACK] Could not find an available channel to play sound or sound is zero-length.")

    except Exception as e:
        print(f"⚠️ [PLAYBACK] Error playing audio with Pygame Sound: {e}")


def _create_wav_in_memory(pcm_data: bytes, rate: int, channels: int, sample_width: int) -> bytes:
    with io.BytesIO() as wav_file_stream:
        with wave.open(wav_file_stream, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)
        return wav_file_stream.getvalue()

def transcribe_segment_elevenlabs_scribe(audio_data: bytes) -> str:
    if not config.elevenlabs_client:
        print("⚠️ [ELEVENLABS_SCRIBE] ElevenLabs client not initialized. Skipping transcription.")
        return "[ElevenLabs Scribe Error: Client not initialized]"
    if not audio_data:
        return ""

    try:
        # Based on the user-provided documentation screenshot for Speech to Text quickstart,
        # the convert method should be called with keyword arguments:
        # file=audio_data and model_id="scribe_v1".
        response = config.elevenlabs_client.speech_to_text.convert(
            file=audio_data,
            model_id="scribe_v1", # As per the documentation screenshot. Ensure this model is appropriate.
            tag_audio_events=False, # Assuming we don't need to tag audio events for this use case.
            
        )

        transcribed_text = ""
        # Expected response structure for elevenlabs-python v1.0+ SpeechToTextResponse
        if hasattr(response, 'text') and isinstance(response.text, str):
            transcribed_text = response.text
        elif isinstance(response, str): # Fallback if response is just a string
            transcribed_text = response
        else:
            print(f"⚠️ [ELEVENLABS_SCRIBE] Unexpected response structure or no text attribute. Full response: {response}")
            # Attempt to serialize if it's a complex object for better logging
            try:
                response_str = str(response) # Default string representation
                if hasattr(response, 'model_dump_json'): # Pydantic model
                    response_str = response.model_dump_json()
                elif hasattr(response, '__dict__'): # Standard object
                    response_str = str(response.__dict__)
                print(f"⚠️ [ELEVENLABS_SCRIBE] Detailed response content: {response_str}")
            except Exception as log_e:
                print(f"⚠️ [ELEVENLABS_SCRIBE] Could not serialize response for detailed logging: {log_e}")


        return transcribed_text
    except Exception as e:
        print(f"⚠️ [ELEVENLABS_SCRIBE] Error during transcription: {e} (Type: {type(e).__name__})")
        return f"[ElevenLabs Scribe Error: {type(e).__name__} - {str(e)}]"

def transcribe_segment(audio_data: bytes) -> str:
    if config.TRANSCRIPTION_PROVIDER == "AZURE":
        if not config.client_az_transcription:
            print("⚠️ [AZURE_TRANSCRIBE] Client not initialized.")
            return "[Azure Transcription Error: Client not initialized]"
        if not audio_data: # audio_data here is expected to be raw PCM
            return ""
        try:
            wav_audio_data = _create_wav_in_memory(
                pcm_data=audio_data,
                rate=config.PYAUDIO_RATE,
                channels=config.PYAUDIO_CHANNELS,
                sample_width=config.PYAUDIO_SAMPLE_WIDTH
            )
            audio_file_tuple = ("audio.wav", io.BytesIO(wav_audio_data), "audio/wav")

            response_text = config.client_az_transcription.audio.transcriptions.create(
                model=config.GPT_4O_TRANSCRIBE_DEPLOYMENT_NAME,
                file=audio_file_tuple,
                language=config.GPT_4O_TRANSCRIBE_LANG_CODE,
                response_format="text"
            )
            # The response for "text" format is directly the string
            return str(response_text) if response_text is not None else ""
        except Exception as e:
            error_message = str(e).lower()
            if "deploymentnotfound" in error_message or "deployment name" in error_message or "could not find deployment" in error_message:
                print(f"☢️ CRITICAL [AZURE_TRANSCRIBE] Deployment '{config.GPT_4O_TRANSCRIBE_DEPLOYMENT_NAME}' not found. Error: {e}")
                return f"[Azure Transcription Error: Deployment '{config.GPT_4O_TRANSCRIBE_DEPLOYMENT_NAME}' not found. Check configuration.]"
            elif "could not infer the audio file type" in error_message or "invalid audio file format" in error_message:
                print(f"⚠️ [AZURE_TRANSCRIBE] Audio format issue. Error: {e}")
                return "[Azure Transcription Error: Audio format issue]"
            elif "authentication" in error_message or "unauthorized" in error_message:
                print(f"⚠️ [AZURE_TRANSCRIBE] Authentication failed. Check AZ_OPENAI_KEY and endpoint. Error: {e}")
                return "[Azure Transcription Error: Authentication]"
            else:
                print(f"⚠️ [AZURE_TRANSCRIBE] Error: {e} (Type: {type(e).__name__}).")
                return f"[Azure Transcription Error: {type(e).__name__}]"
    elif config.TRANSCRIPTION_PROVIDER == "ELEVENLABS":
        if not audio_data: # audio_data here is raw PCM
            return ""
        
        wav_audio_data = _create_wav_in_memory(
            pcm_data=audio_data,
            rate=config.PYAUDIO_RATE,
            channels=config.PYAUDIO_CHANNELS,
            sample_width=config.PYAUDIO_SAMPLE_WIDTH
        )
        
        if not wav_audio_data:
            print("⚠️ [TRANSCRIBE_SEGMENT_EL]' WAV conversion resulted in empty data for ElevenLabs. Returning empty.")
            return ""
            
        return transcribe_segment_elevenlabs_scribe(wav_audio_data)
    else:
        print(f"⚠️ [TRANSCRIBE] Unknown TRANSCRIPTION_PROVIDER: {config.TRANSCRIPTION_PROVIDER}. Skipping transcription.")
        return "[Transcription Error: Unknown provider]"

def pyaudio_callback(in_data, frame_count, time_info, status):
    if globals.audio_capture_active.is_set():
        with globals.audio_buffer_lock:
            globals.full_audio_data.extend(in_data)

        # Send to WebSocket if connected and speech is active
        # globals.ws_app is set by on_ws_open
        if globals.ws_app and globals.ws_app.sock and globals.ws_app.sock.connected:
            try:
                if globals.speech_active.is_set() and not globals.first_audio_packet_sent_this_utterance:
                    print(f"🎤 [AUDIO_CAPTURE_SEND_WS] Sending first audio packet ({len(in_data)} bytes) to WebSocket for this utterance.")
                    globals.first_audio_packet_sent_this_utterance = True
                
                globals.ws_app.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(in_data).decode("utf-8")
                }))
            except websocket.WebSocketConnectionClosedException:
                # print("🎤 [AUDIO_CAPTURE_SEND_WS] WebSocket closed while trying to send audio.")
                pass # Expected if connection closes mid-send
            except Exception as e:
                # print(f"🎤 [AUDIO_CAPTURE_SEND_WS] Error sending audio to WebSocket: {e}")
                pass # Avoid spamming logs for minor send errors
    return (None, pyaudio.paContinue)
