import json
import time
import websocket # For ws type hint

from . import config
from . import globals
from .audio_processing import transcribe_segment # Relative import

def on_ws_open(ws: websocket.WebSocketApp):
    globals.ws_app = ws # Store the WebSocketApp instance globally for pyaudio_callback
    print("🎤 [WEBSOCKET] WebSocket Opened. Configuring session...")

    # Reset states for a new session
    globals.utterance_start_time_monotonic = None
    globals.utterance_audio_start_byte_offset = 0
    globals.current_sdk_interim_text = ""
    globals.last_periodic_transcription_time = 0.0 # Reset for periodic transcription logic
    globals.speech_active.clear()
    globals.first_audio_packet_sent_this_utterance = False

    # Configure the WebSocket session for transcription
    ws.send(json.dumps({
        "type": "transcription_session.update",
        "session": {
            "input_audio_format": "pcm16", # Matches PyAudio config
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5, # Adjust as needed
                "prefix_padding_ms": 300, # How much audio before speech starts is included
                "silence_duration_ms": 2000 # How long silence before speech_stopped
            },
            "input_audio_noise_reduction": {"type": "near_field"} # Or "far_field"
        }
    }))
    print("🎤 [WEBSOCKET] WebSocket session configured.")


def on_ws_message(ws: websocket.WebSocketApp, message_str: str):
    try:
        data = json.loads(message_str)
        msg_type = data.get("type")

        if msg_type == "input_audio_buffer.speech_started":
            print("\n🟢 [WEBSOCKET_EVENT] Speech Started")
            globals.speech_active.set()
            globals.first_audio_packet_sent_this_utterance = False # Reset for this new utterance
            globals.utterance_start_time_monotonic = time.monotonic()
            globals.current_sdk_interim_text = "" # Reset interim text for new utterance
            globals.last_periodic_transcription_time = globals.utterance_start_time_monotonic # Reset for periodic
            globals.last_periodic_transcription_byte_offset = globals.utterance_audio_start_byte_offset

            with globals.audio_buffer_lock:
                # Calculate pre-roll: audio from a bit before speech started
                pre_roll_bytes = int(config.PYAUDIO_RATE * (config.PRE_ROLL_MS / 1000) * config.PYAUDIO_SAMPLE_WIDTH * config.PYAUDIO_CHANNELS)
                current_buffer_len = len(globals.full_audio_data)
                globals.utterance_audio_start_byte_offset = max(0, current_buffer_len - pre_roll_bytes)
            
            actual_pre_roll_duration_s = (len(globals.full_audio_data) - globals.utterance_audio_start_byte_offset) / (config.PYAUDIO_RATE * config.PYAUDIO_SAMPLE_WIDTH * config.PYAUDIO_CHANNELS) if config.PYAUDIO_RATE > 0 else 0
            print(f"🎤 [WEBSOCKET_EVENT] Pre-roll audio start offset: {globals.utterance_audio_start_byte_offset} (actual pre-roll: {actual_pre_roll_duration_s:.2f}s)")


        elif msg_type == "input_audio_buffer.speech_stopped":
            print("\n🔴 [WEBSOCKET_EVENT] Speech Stopped")
            globals.speech_active.clear()

            final_audio_segment = b""
            sdk_text_at_stop = globals.current_sdk_interim_text # Capture current SDK text

            if globals.utterance_start_time_monotonic is not None:
                with globals.audio_buffer_lock:
                    # Ensure start offset is valid relative to current buffer length
                    if 0 <= globals.utterance_audio_start_byte_offset < len(globals.full_audio_data):
                        final_audio_segment = globals.full_audio_data[globals.utterance_audio_start_byte_offset : len(globals.full_audio_data)]
                    elif len(globals.full_audio_data) > 0: # If offset is bad but buffer has data
                        print(f"⚠️ [WEBSOCKET_EVENT] Warning: utterance_audio_start_byte_offset ({globals.utterance_audio_start_byte_offset}) invalid with buffer len {len(globals.full_audio_data)}. Using full buffer for final.")
                        final_audio_segment = globals.full_audio_data[:] # Fallback to full buffer
                    else: # No audio data in buffer
                        print("⚠️ [WEBSOCKET_EVENT] Warning: No audio data in buffer at speech_stopped.")
            else:
                print("⚠️ [WEBSOCKET_EVENT] Warning: Speech stopped but no start time recorded (utterance_start_time_monotonic is None).")

            segment_id = globals.get_next_segment_id() # Get segment ID for the final segment

            if final_audio_segment:
                # print(f"🧠 [{config.TRANSCRIPTION_PROVIDER}_TRANSCRIBE_TASK] Segment {segment_id}: Transcribing final segment ({len(final_audio_segment)} bytes)...")
                text_4o_final = transcribe_segment(final_audio_segment)
                print(f"🧠 [{config.TRANSCRIPTION_PROVIDER}_TRANSCRIBE_RESULT] Segment {segment_id}: Final transcription: \"{text_4o_final}\"")
                
                globals.transcription_to_translation_queue.put((segment_id, sdk_text_at_stop, text_4o_final))
            elif sdk_text_at_stop: 
                print(f"ℹ️ [WEBSOCKET_EVENT] Segment {segment_id}: No audio for 4o, using SDK text for final. SDK: \"{sdk_text_at_stop}\"")
                globals.transcription_to_translation_queue.put((segment_id, sdk_text_at_stop, "")) 
            else:
                print(f"ℹ️ [WEBSOCKET_EVENT] Segment {segment_id}: Speech stopped, no audio segment captured for 4o, and no interim SDK text. Nothing to queue as final.")

            # Reset for next utterance
            globals.utterance_start_time_monotonic = None
            globals.current_sdk_interim_text = ""


        elif msg_type == "conversation.item.input_audio_transcription.delta":
            delta_text = data.get("delta", "")
            if delta_text:
                print(delta_text, end="", flush=True) # This is the [WEBSOCKET_RECV_DELTA]
                globals.current_sdk_interim_text += delta_text

        elif msg_type == "conversation.item.input_audio_transcription.completed":
            # This is the final transcription from the WebSocket SDK itself
            final_sdk_text_ws = data.get("transcript", "")
            print(f"\n✅ [WEBSOCKET_RECV_COMPLETED] WS SDK Final Text (informational): \"{final_sdk_text_ws}\"")
            # We use current_sdk_interim_text accumulated from deltas for our logic,
            # but this message confirms the end of the SDK's transcription for the utterance.

        elif msg_type == "transcription_session.started":
            print(f"ℹ️ [WEBSOCKET_EVENT] Session Started: ID {data.get('session', {}).get('id')}")
        elif msg_type == "transcription_session.stopped":
            print(f"ℹ️ [WEBSOCKET_EVENT] Session Stopped: ID {data.get('session', {}).get('id')}")
        elif msg_type == "error":
            print(f"❌ [WEBSOCKET_ERROR] Message: {data.get('code')} - {data.get('message')}")
            if data.get('code') == "InvalidAuthToken" or data.get('code') == "InvalidApiKey":
                print("☢️ CRITICAL: WebSocket Authentication Failed. Check AZ_OPENAI_KEY and WebSocket header configuration.")
                # Potentially set globals.done = True here or signal main thread to stop

    except json.JSONDecodeError:
        print(f"⚠️ [WEBSOCKET_ERROR] Could not decode JSON: {message_str}")
    except Exception as e:
        print(f"⚠️ [WEBSOCKET_ERROR] Error processing message: {e}. Message: {message_str}")


def on_ws_error(ws: websocket.WebSocketApp, error: Exception):
    print(f"❌ [WEBSOCKET_ERROR] Connection Error: {error}")
    # Consider setting globals.done = True if error is fatal

def on_ws_close(ws: websocket.WebSocketApp, close_status_code: int | None, close_msg: str | None):
    print(f"🔌 [WEBSOCKET] Closed: Status {close_status_code}, Msg: {close_msg}")
    globals.done = True # Signal other threads and main loop to stop
    globals.ws_app = None # Clear the global ws_app instance
