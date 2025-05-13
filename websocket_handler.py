import json
import time
import queue
import websocket  # For WebSocketApp type hint

import config as config
import globals as app_globals
from audio_utils import transcribe_with_scribe, validate_transcription

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
    app_globals.final_transcription_pending_for_current_utterance.clear()

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
            app_globals.schedule_gui_update("speaking_status", True)  # GUI Update
            app_globals.final_transcription_pending_for_current_utterance.set()
            app_globals.utterance_start_time_monotonic = time.monotonic()
            
            with app_globals.audio_buffer_lock:
                # Calculate pre-roll: audio from a bit before speech started
                pre_roll_bytes = int(config.PYAUDIO_RATE * (config.AZ_VAD_PRE_ROLL_MS / 1000) * 
                                    config.PYAUDIO_SAMPLE_WIDTH * config.PYAUDIO_CHANNELS)
                current_buffer_len = len(app_globals.full_audio_data)
                app_globals.utterance_audio_start_byte_offset = max(0, current_buffer_len - pre_roll_bytes)
                
                # Reset last_periodic_scribe_chunk_end_byte_offset to the start of the new utterance
                app_globals.last_periodic_scribe_chunk_end_byte_offset = app_globals.utterance_audio_start_byte_offset
            
            # Reset periodic scribe tracking for new utterance
            app_globals.last_periodic_scribe_submission_time = app_globals.utterance_start_time_monotonic

        elif msg_type == "input_audio_buffer.speech_stopped":
            speech_duration_s = 0.0
            if app_globals.utterance_start_time_monotonic is not None:
                speech_duration_s = time.monotonic() - app_globals.utterance_start_time_monotonic
            print(f"\n🔴 [WS_VAD_EVENT] Speech Stopped (Duration: {speech_duration_s:.2f}s)")
            
            app_globals.schedule_gui_update("speaking_status", False)  # GUI Update

            if not app_globals.final_transcription_pending_for_current_utterance.is_set():
                print("ℹ️ [SCRIBE_FINAL_TASK] Final transcription for this utterance already processed or not pending. Skipping.")
                app_globals.speech_active.clear()
                return

            app_globals.final_transcription_pending_for_current_utterance.clear()
            app_globals.speech_active.clear()

            final_audio_segment_pcm = b""
            current_buffer_len = 0

            with app_globals.audio_buffer_lock:
                current_buffer_len = len(app_globals.full_audio_data)
            
            if app_globals.utterance_start_time_monotonic is not None and current_buffer_len > 0:
                # Calculate the pre-roll for the final segment based on FINAL_SCRIBE_PRE_ROLL_MS
                final_segment_overlap_bytes = int(config.PYAUDIO_RATE * 
                                                  (config.FINAL_SCRIBE_PRE_ROLL_MS / 1000) *
                                                  config.PYAUDIO_SAMPLE_WIDTH * 
                                                  config.PYAUDIO_CHANNELS)

                # Determine the start byte for the final transcription segment
                start_byte_final = max(
                    app_globals.utterance_audio_start_byte_offset, 
                    app_globals.last_periodic_scribe_chunk_end_byte_offset - final_segment_overlap_bytes
                )
                start_byte_final = max(0, start_byte_final)
                start_byte_final = min(start_byte_final, current_buffer_len)

                if start_byte_final < current_buffer_len:
                    with app_globals.audio_buffer_lock:
                        final_audio_segment_pcm = app_globals.full_audio_data[start_byte_final : current_buffer_len]
                else:
                    if app_globals.last_periodic_scribe_chunk_end_byte_offset == app_globals.utterance_audio_start_byte_offset:
                        with app_globals.audio_buffer_lock:
                            final_audio_segment_pcm = app_globals.full_audio_data[app_globals.utterance_audio_start_byte_offset : current_buffer_len]

            if final_audio_segment_pcm:
                print(f"🎤 [SCRIBE_FINAL_TASK] Transcribing final audio segment ({len(final_audio_segment_pcm)} bytes).")
                transcribed_text_final = transcribe_with_scribe(
                    final_audio_segment_pcm, 
                    is_final_segment=True
                )
                
                if validate_transcription(transcribed_text_final):
                    print(f"🎤 [SCRIBE_FINAL_RESULT] Final transcription: \"{transcribed_text_final}\"")
                    app_globals.scribe_to_translator_llm_queue.put(transcribed_text_final)
                    app_globals.schedule_gui_update("transcription", f"[Final] {transcribed_text_final}")  # GUI Update
                    with app_globals.recent_scribe_transcriptions_lock:
                        app_globals.recent_scribe_transcriptions.append(transcribed_text_final)
                    if app_globals.all_scribe_transcriptions_log is not None:
                        app_globals.all_scribe_transcriptions_log.append(f"[FINAL] {transcribed_text_final}")
                else:
                    print(f"⚠️ [SCRIBE_FINAL_RESULT] Invalid or empty final transcription: \"{transcribed_text_final}\". Not queueing for LLM.")
            else:
                print("ℹ️ [SCRIBE_FINAL_TASK] No audio segment captured for final Scribe transcription.")

            app_globals.utterance_start_time_monotonic = None
            app_globals.utterance_audio_start_byte_offset = 0

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
