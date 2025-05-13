import json
import base64
import io
import wave
import pyaudio # For pyaudio.paContinue
import websocket # For WebSocketConnectionClosedException type hint
from elevenlabs import VoiceSettings
import numpy as np # For audio data manipulation

import config as config
import globals as app_globals

def _create_wav_in_memory(pcm_data: bytes, rate: int, channels: int, sample_width: int) -> bytes:
    """Convert raw PCM data to WAV format in memory"""
    with io.BytesIO() as wav_file_stream:
        with wave.open(wav_file_stream, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)
        return wav_file_stream.getvalue()

def validate_transcription(transcribed_text: str) -> bool:
    """
    Validate if a transcription is usable (not empty, no errors, no replacement characters).
    
    Args:
        transcribed_text: The text returned from the transcription service
        
    Returns:
        bool: True if the transcription is valid, False otherwise
    """
    if not transcribed_text:
        return False
        
    if transcribed_text.startswith("[Scribe Error:"):
        return False
        
    if "\uFFFD" in transcribed_text:  # Filter out replacement characters
        return False
        
    return True

def transcribe_with_scribe(audio_data: bytes, is_final_segment: bool) -> str:
    """Transcribe audio using ElevenLabs Scribe with word-level processing."""
    if not config.elevenlabs_client:
        print("⚠️ [SCRIBE] ElevenLabs client not initialized. Skipping transcription.")
        return "[Scribe Error: Client not initialized]"
    if not audio_data:
        return ""

    try:
        wav_audio_data = audio_data
        if not audio_data.startswith(b'RIFF'): # Check if already WAV
            wav_audio_data = _create_wav_in_memory(
                pcm_data=audio_data,
                rate=config.PYAUDIO_RATE,
                channels=config.PYAUDIO_CHANNELS,
                sample_width=config.PYAUDIO_SAMPLE_WIDTH
            )
            
        response = config.elevenlabs_client.speech_to_text.convert(
            file=wav_audio_data,
            model_id=config.ELEVENLABS_SCRIBE_MODEL_ID,
            tag_audio_events=False, # Assuming we don't need to tag audio events
            language_code=config.SCRIBE_LANGUAGE_CODE
        )

        # New logic to process 'words' array
        if hasattr(response, 'words') and isinstance(response.words, list) and response.words:
            words_list = response.words
            
            # 1. Find the index of the first actual "word" type item
            first_word_item_index = -1
            for i, word_obj in enumerate(words_list):
                if hasattr(word_obj, 'type') and word_obj.type == "word":
                    first_word_item_index = i
                    break
            
            if first_word_item_index == -1: # No "word" items found
                return ""

            # 2. Define candidate_words: ALWAYS start from the first word item found in this chunk.
            candidate_words = words_list[first_word_item_index:]

            if not candidate_words:
                return ""

            # 3. Apply end trimming based on is_final_segment
            if is_final_segment:
                # For the FINAL segment, we keep ALL words, including the last one
                print(f"ℹ️ [SCRIBE_FINAL] Processing final segment, keeping ALL {len(candidate_words)} candidate words")
                final_words_to_process = candidate_words
            else:
                # For NON-FINAL segments (periodic), remove the last word to prevent cut-offs
                last_word_item_index_in_candidate = -1
                for i in range(len(candidate_words) - 1, -1, -1):
                    word_obj = candidate_words[i]
                    if hasattr(word_obj, 'type') and word_obj.type == "word":
                        last_word_item_index_in_candidate = i
                        break
                
                if last_word_item_index_in_candidate > 0:
                    # Keep all items before the last word (excluding the last word)
                    final_words_to_process = candidate_words[:last_word_item_index_in_candidate]
                    print(f"ℹ️ [SCRIBE_PERIODIC] Removed last word at position {last_word_item_index_in_candidate} of {len(candidate_words)}")
                else:
                    final_words_to_process = []
                    print(f"ℹ️ [SCRIBE_PERIODIC] No complete words to keep after trimming the last word")
            
            if not final_words_to_process:
                return ""
            
            # 4. Join the .text attribute of the remaining items
            result = "".join(word_obj.text for word_obj in final_words_to_process if hasattr(word_obj, 'text'))
            
            if not result: # If result is empty string after join
                return ""

            if is_final_segment:
                print(f"ℹ️ [SCRIBE_FINAL] Final transcription result: \"{result}\"")
                return result
            else: # It's periodic and result is not empty
                processed_result = result + "..."
                print(f"ℹ️ [SCRIBE_PERIODIC] Transcription with ellipsis: \"{processed_result}\"")
                return processed_result

        # Fallback to the main 'text' field if 'words' array is not usable or new logic results in empty
        # (though an empty result from word processing might be intended)
        elif hasattr(response, 'text') and isinstance(response.text, str):
            print("ℹ️ [SCRIBE] Processed using 'words' array resulted in empty or 'words' array not suitable, falling back to main 'text' field.")
            text_content = response.text
            
            if not text_content: # If fallback text is empty
                return ""

            if is_final_segment:
                print(f"ℹ️ [SCRIBE_FINAL] Final transcription result (from 'text' fallback): \"{text_content}\"")
                return text_content
            else: # Periodic and text_content is not empty
                processed_text = text_content + "..."
                print(f"ℹ️ [SCRIBE_PERIODIC] Transcription with ellipsis (from 'text' fallback): \"{processed_text}\"")
                return processed_text
        elif isinstance(response, str): # Fallback if response is just a string
            str_content = response

            if not str_content: # If fallback string is empty
                return ""

            # If the string response is one of our own error messages, return it as is.
            if str_content.startswith("[Scribe Error:"):
                return str_content

            if is_final_segment:
                print(f"ℹ️ [SCRIBE_FINAL] Final transcription result (from string fallback): \"{str_content}\"")
                return str_content
            else: # Periodic and str_content is not empty and not an error
                processed_str = str_content + "..."
                print(f"ℹ️ [SCRIBE_PERIODIC] Transcription with ellipsis (from string fallback): \"{processed_str}\"")
                return processed_str
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

def generate_audio_elevenlabs(text: str, segment_id: int) -> bytes | None:
    """Generate audio using ElevenLabs TTS."""
    if not config.elevenlabs_client:
        print(f"⚠️ [TTS_WORKER_EL ({segment_id})] ElevenLabs client not initialized.")
        return None
    if not config.ELEVENLABS_VOICE_ID:
        print(f"⚠️ [TTS_WORKER_EL ({segment_id})] ElevenLabs Voice ID not configured.")
        return None
    if not text or not text.strip():
        print(f"ℹ️ [TTS_WORKER_EL ({segment_id})] No text to synthesize.")
        return None

    try:
        print(f"🎤 [TTS_WORKER_EL ({segment_id})] Synthesizing: \"{text[:50]}...\"")
        audio_stream = config.elevenlabs_client.text_to_speech.convert(
            voice_id=config.ELEVENLABS_VOICE_ID,
            text=text,
            model_id=config.ELEVENLABS_MODEL_ID,
            output_format=config.ELEVENLABS_OUTPUT_FORMAT,  # Use configured output format
            language_code=config.TTS_LANGUAGE_CODE,  # Use TTS_LANGUAGE_CODE for TTS language
            voice_settings=VoiceSettings(
                stability=1,
                similarity_boost=0.9,
                style=0.0,  # Adjust if style exaggeration is needed
                use_speaker_boost=True,
                speed=1.2  # Slightly faster for real-time feel
            )
        )
        
        audio_bytes = b"".join([chunk for chunk in audio_stream])
        print(f"🎧 [TTS_WORKER_EL ({segment_id})] Audio generated ({len(audio_bytes)} bytes).")
        return audio_bytes
    except Exception as e:
        print(f"⚠️ [TTS_WORKER_EL ({segment_id})] Error generating audio: {e}")
        return None

def play_audio_pygame(audio_bytes: bytes, segment_id: int):
    """Play audio bytes using Pygame mixer."""
    if not app_globals.pygame_mixer_initialized.is_set():
        print(f"⚠️ [PLAYBACK_WORKER ({segment_id})] Pygame mixer not initialized. Cannot play audio.")
        return
    if not audio_bytes:
        print(f"ℹ️ [PLAYBACK_WORKER ({segment_id})] No audio data to play.")
        return

    try:
        print(f"🔊 [PLAYBACK_WORKER ({segment_id})] Playing audio ({len(audio_bytes)} bytes)...")

        processed_audio_bytes = audio_bytes
        source_audio_rate = config.PYAUDIO_RATE # Expected to be 16000 for TTS
        source_audio_channels = 1 # TTS output is mono
        # Assuming 16-bit PCM from TTS (config.ELEVENLABS_OUTPUT_FORMAT = "pcm_16000")
        # Pygame size -16 means signed 16-bit. np.int16 is signed 16-bit.
        source_dtype = np.int16 
        
        if app_globals.pygame.mixer.get_init():
            actual_mixer_freq, actual_mixer_format_bitsize, actual_mixer_channels = app_globals.pygame.mixer.get_init()
            
            # Convert raw bytes to numpy array based on source format
            current_samples = np.frombuffer(processed_audio_bytes, dtype=source_dtype)

            # 1. Channel Conversion (if necessary)
            if actual_mixer_channels == 2 and source_audio_channels == 1:
                current_samples = np.repeat(current_samples, 2) # Duplicate samples for L and R
                # After this, current_samples is stereo, matching actual_mixer_channels
            elif actual_mixer_channels == 1 and source_audio_channels == 2:
                 print(f"⚠️ [PLAYBACK_WORKER ({segment_id})] Mixer is mono, audio is stereo. This might not play correctly. Playing as is (first channel if samples are interleaved).")
                 # Potentially take only one channel: current_samples = current_samples[::2] or current_samples[1::2]
            elif actual_mixer_channels != source_audio_channels:
                 print(f"⚠️ [PLAYBACK_WORKER ({segment_id})] Channel mismatch: Mixer {actual_mixer_channels}ch, Source {source_audio_channels}ch. Playing as is.")

            # 2. Resampling (if necessary)
            if actual_mixer_freq != source_audio_rate:
                num_source_samples = len(current_samples)
                if actual_mixer_channels == 2 and source_audio_channels == 1: # if we converted mono to stereo
                    num_source_samples //= 2 # number of frames

                # Calculate new number of samples for the target frequency
                num_target_samples = int(round(num_source_samples * actual_mixer_freq / source_audio_rate))
                
                resampled_audio_list = []

                if (actual_mixer_channels == 2 and source_audio_channels == 1) or \
                   (actual_mixer_channels == 2 and source_audio_channels == 2): # Stereo processing
                    # Separate channels if stereo, resample, then interleave
                    # current_samples would be stereo here if converted or if source was stereo
                    left_channel = current_samples[0::2]
                    right_channel = current_samples[1::2]
                    
                    x_source = np.linspace(0, 1, len(left_channel))
                    x_target = np.linspace(0, 1, num_target_samples)
                    
                    resampled_left = np.interp(x_target, x_source, left_channel)
                    resampled_right = np.interp(x_target, x_source, right_channel)
                    
                    # Interleave L and R channels
                    resampled_stereo = np.empty(num_target_samples * 2, dtype=source_dtype)
                    resampled_stereo[0::2] = resampled_left
                    resampled_stereo[1::2] = resampled_right
                    current_samples = resampled_stereo.astype(source_dtype)

                elif actual_mixer_channels == 1: # Mono processing
                    x_source = np.linspace(0, 1, num_source_samples) # num_source_samples is correct here
                    x_target = np.linspace(0, 1, num_target_samples)
                    current_samples = np.interp(x_target, x_source, current_samples).astype(source_dtype)
                
                else: # Should not happen if previous channel logic is correct
                    print(f"⚠️ [PLAYBACK_WORKER ({segment_id})] Unexpected channel configuration for resampling. Skipping resampling.")

            processed_audio_bytes = current_samples.tobytes()

        sound = app_globals.pygame.mixer.Sound(buffer=processed_audio_bytes)
        channel = sound.play()
        if channel:
            while channel.get_busy():
                app_globals.pygame.time.Clock().tick(10) # Keep alive, prevent busy loop
        else:
            print(f"⚠️ [PLAYBACK_WORKER ({segment_id})] Could not get a channel to play audio.")
        print(f"✅ [PLAYBACK_WORKER ({segment_id})] Playback finished.")
    except Exception as e:
        print(f"⚠️ [PLAYBACK_WORKER ({segment_id})] Error playing audio: {e}")
