import json
import time
import queue
import websocket  # For WebSocketApp type hint

from . import config_new as config
from . import globals_new as app_globals
from .audio_utils_new import transcribe_with_scribe

def on_ws_open_new(ws: websocket.WebSocketApp):
    """Handler for when the WebSocket connection opens"""
    app_globals.ws_app = ws
    print("🎤 [WEBSOCKET] WebSocket Opened. Configuring session...")

    # Reset states for a new session
    app_globals.utterance_start_time_monotonic = None
    app_globals.utterance_audio_start_byte_offset = 0
    app_globals.last_periodic_scribe_submission_time = 0.0
    app_globals.last_periodic_scribe_chunk_end_byte_offset = 0
    app_globals.speech_active.clear()

    with app_globals.audio_buffer_lock:
        app_globals.full_audio_data.clear()  # Clear audio buffer for new session
    
    # Initialize recent_scribe_transcriptions with correct maxlen from config
    app_globals.recent_scribe_transcriptions = queue.deque(maxlen=config.LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE)

    # Configure the WebSocket session for VAD detection
    ws.send(json.dumps({
        "type": "transcription_session.update",
        "session": {
            "input_audio_format": "pcm16",  # Matches PyAudio config
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,  # Adjust as needed
                "prefix_padding_ms": config.AZ_VAD_PRE_ROLL_MS,  # How much audio before speech starts is included
                "silence_duration_ms": config.AZ_VAD_SILENCE_TIMEOUT_MS  # How long silence before speech_stopped
            },
            "input_audio_noise_reduction": {"type": "near_field"}  # Or "far_field"
        }
    }))
    print("🎤 [WEBSOCKET] WebSocket session configured for VAD.")


def on_ws_message_new(ws: websocket.WebSocketApp, message_str: str):
    """Handler for incoming WebSocket messages"""
    try:
        data = json.loads(message_str)
        msg_type = data.get("type")

        if msg_type == "input_audio_buffer.speech_started":
            print("\n🟢 [WS_VAD_EVENT] Speech Started")
            app_globals.speech_active.set()
            app_globals.utterance_start_time_monotonic = time.monotonic()
            
            with app_globals.audio_buffer_lock:
                # Calculate pre-roll: audio from a bit before speech started
                pre_roll_bytes = int(config.PYAUDIO_RATE * (config.AZ_VAD_PRE_ROLL_MS / 1000) * 
                                    config.PYAUDIO_SAMPLE_WIDTH * config.PYAUDIO_CHANNELS)
                current_buffer_len = len(app_globals.full_audio_data)
                app_globals.utterance_audio_start_byte_offset = max(0, current_buffer_len - pre_roll_bytes)
            
            # Reset periodic scribe tracking for new utterance
            app_globals.last_periodic_scribe_submission_time = app_globals.utterance_start_time_monotonic
            app_globals.last_periodic_scribe_chunk_end_byte_offset = app_globals.utterance_audio_start_byte_offset

            bytes_of_preroll = len(app_globals.full_audio_data) - app_globals.utterance_audio_start_byte_offset
            actual_pre_roll_ms = (bytes_of_preroll / 
                                 (config.PYAUDIO_RATE * config.PYAUDIO_SAMPLE_WIDTH * config.PYAUDIO_CHANNELS)) * 1000
            
            # Removed the "Actual pre-roll" log message

        elif msg_type == "input_audio_buffer.speech_stopped":
            print("\n🔴 [WS_VAD_EVENT] Speech Stopped")
            
            # Get the duration of this speech segment
            if app_globals.utterance_start_time_monotonic is not None:
                speech_duration = time.monotonic() - app_globals.utterance_start_time_monotonic
                print(f"🔴 [WS_VAD_EVENT] Speech duration: {speech_duration:.2f} seconds")
            
            # Clear the flag AFTER we extract audio to ensure we capture everything
            current_buffer_len = 0
            with app_globals.audio_buffer_lock:
                current_buffer_len = len(app_globals.full_audio_data)
            
            final_audio_segment_pcm = b""
            if app_globals.utterance_start_time_monotonic is not None:
                with app_globals.audio_buffer_lock:
                    final_pre_roll_bytes = int(config.PYAUDIO_RATE * (config.FINAL_SCRIBE_PRE_ROLL_MS / 1000) * 
                                              config.PYAUDIO_SAMPLE_WIDTH * config.PYAUDIO_CHANNELS)
                    
                    # Get the earliest possible start_byte: either from utterance start or using pre-roll
                    start_byte_final = max(app_globals.utterance_audio_start_byte_offset, 
                                          current_buffer_len - final_pre_roll_bytes)
                    start_byte_final = min(start_byte_final, current_buffer_len)  # Safety check

                    if start_byte_final < current_buffer_len and current_buffer_len > 0:
                        final_audio_segment_pcm = app_globals.full_audio_data[start_byte_final:current_buffer_len]
                        print(f"🎤 [SCRIBE_FINAL_TASK] Extracted final audio for Scribe.")
                    else:
                        print("⚠️ [SCRIBE_FINAL_TASK] No audio data for final Scribe transcription.")
            else:
                print("⚠️ [SCRIBE_FINAL_TASK] Speech stopped but no VAD start time recorded.")
            
            # Now clear the speech active flag
            app_globals.speech_active.clear()

            if final_audio_segment_pcm:
                print(f"🎤 [SCRIBE_FINAL_TRANSCRIBE] Transcribing final audio segment.")
                transcribed_text_final = transcribe_with_scribe(final_audio_segment_pcm)
                
                if transcribed_text_final and not transcribed_text_final.startswith("[Scribe Error:"):
                    print(f"🎤 [SCRIBE_FINAL_RESULT] Final transcription: \"{transcribed_text_final}\"")
                    
                    # Put into the queue for the LLM Translator Agent
                    app_globals.scribe_to_translator_llm_queue.put(transcribed_text_final)
                    
                    # Store in recent transcriptions list
                    with app_globals.recent_scribe_transcriptions_lock:
                        app_globals.recent_scribe_transcriptions.append(transcribed_text_final)
                    
                    if app_globals.all_scribe_transcriptions_log is not None:
                        app_globals.all_scribe_transcriptions_log.append(f"[FINAL] {transcribed_text_final}")
                else:
                    print(f"⚠️ [SCRIBE_FINAL_RESULT] Error or empty transcription: {transcribed_text_final}")
            else:
                print("ℹ️ [SCRIBE_FINAL_TASK] No audio segment captured for final Scribe transcription.")

            # Reset for next utterance
            app_globals.utterance_start_time_monotonic = None

        elif msg_type == "transcription_session.started":
            print(f"ℹ️ [WEBSOCKET_EVENT] Session Started: ID {data.get('session', {}).get('id')}")
        elif msg_type == "transcription_session.stopped":
            print(f"ℹ️ [WEBSOCKET_EVENT] Session Stopped: ID {data.get('session', {}).get('id')}")
        elif msg_type == "error":
            print(f"❌ [WEBSOCKET_ERROR] Message: {data.get('code')} - {data.get('message')}")
            if data.get('code') == "InvalidAuthToken" or data.get('code') == "InvalidApiKey":
                print("☢️ CRITICAL: WebSocket Authentication Failed. Check AZ_OPENAI_KEY configuration.")

    except json.JSONDecodeError:
        print(f"⚠️ [WEBSOCKET_ERROR] Could not decode JSON: {message_str}")
    except Exception as e:
        print(f"⚠️ [WEBSOCKET_ERROR] Error processing message: {e}. Message: {message_str}")


def on_ws_error_new(ws: websocket.WebSocketApp, error: Exception):
    """Handler for WebSocket errors"""
    print(f"❌ [WEBSOCKET_ERROR] Connection Error: {error}")


def on_ws_close_new(ws: websocket.WebSocketApp, close_status_code: int | None, close_msg: str | None):
    """Handler for when the WebSocket connection closes"""
    print(f"🔌 [WEBSOCKET] Closed: Status {close_status_code}, Msg: {close_msg}")
    app_globals.done.set()  # Signal other threads and main loop to stop
    app_globals.ws_app = None  # Clear the global ws_app instance
