import threading
import time
import pyaudio
import websocket
import os
import sys

# Fix imports to work both when run directly and as part of a package
if __name__ == "__main__":
    # Add the parent directory to sys.path to enable absolute imports
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Use absolute imports when run directly
    from new_dub import config_new as config
    from new_dub import globals_new as app_globals
    from new_dub.workers_new import (
        periodic_scribe_transcription_worker_new,
        translator_llm_agent_worker_new
    )
    from new_dub.audio_utils_new import pyaudio_callback_new
    from new_dub.websocket_handler_new import (
        on_ws_open_new,
        on_ws_message_new,
        on_ws_error_new,
        on_ws_close_new
    )
else:
    # Use relative imports when imported as part of a package
    from . import config_new as config
    from . import globals_new as app_globals
    from .workers_new import (
        periodic_scribe_transcription_worker_new,
        translator_llm_agent_worker_new
    )
    from .audio_utils_new import pyaudio_callback_new
    from .websocket_handler_new import (
        on_ws_open_new,
        on_ws_message_new,
        on_ws_error_new,
        on_ws_close_new
    )

def select_input_device():
    """Simple interactive input device selection"""
    p = pyaudio.PyAudio()
    
    print("=== Available Input Devices ===")
    input_devices = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info.get('maxInputChannels', 0) > 0:
            input_devices.append({'index': i, 'name': info['name']})
            print(f"{i}: {info['name']}")
    
    selected_input_idx_str = input("Select Input Device [PyAudio index]: ")
    try:
        idx_in = int(selected_input_idx_str)
        if not any(dev['index'] == idx_in for dev in input_devices):
            print(f"Invalid input device index: {idx_in}. Using default device.")
            idx_in = None
        else:
            print(f"🎤 Input device selected: #{idx_in} - {p.get_device_info_by_index(idx_in)['name']}")
    except ValueError:
        print(f"Invalid input: '{selected_input_idx_str}'. Using default device.")
        idx_in = None
    
    p.terminate()
    return idx_in

def main_new_dub():
    """Main function for the new_dub application"""
    print("🚀 Starting New Dub Application...")

    if not config.AZ_OPENAI_ENDPOINT or not config.AZ_OPENAI_KEY:
        print("❌ CRITICAL: Azure OpenAI endpoint or key not configured. Cannot continue.")
        return

    if not config.ELEVENLABS_API_KEY:
        print("❌ CRITICAL: ElevenLabs API key not configured. Cannot continue.")
        return

    # Get input device selection
    config.PYAUDIO_INPUT_DEVICE_INDEX = select_input_device()

    # --- Start Worker Threads ---
    print("🧵 Starting worker threads...")
    periodic_scribe_thread = threading.Thread(target=periodic_scribe_transcription_worker_new, daemon=True)
    periodic_scribe_thread.start()

    translator_agent_thread = threading.Thread(target=translator_llm_agent_worker_new, daemon=True)
    translator_agent_thread.start()

    # --- PyAudio Setup ---
    p_audio = pyaudio.PyAudio()
    stream = None
    try:
        stream = p_audio.open(
            format=config.PYAUDIO_FORMAT,
            channels=config.PYAUDIO_CHANNELS,
            rate=config.PYAUDIO_RATE,
            input=True,
            input_device_index=config.PYAUDIO_INPUT_DEVICE_INDEX,
            frames_per_buffer=config.PYAUDIO_FRAMES_PER_BUFFER,
            stream_callback=pyaudio_callback_new
        )
        stream.start_stream()
        print("🎤 PyAudio Stream Started.")
    except Exception as e:
        print(f"❌ PYAUDIO_ERROR: Failed to open or start stream: {e}")
        app_globals.done.set()

    # --- WebSocket Setup ---
    ws_thread = None
    if not app_globals.done.is_set():
        print(f"🔌 Connecting to WebSocket: {config.WS_URL}")
        ws_header = {"api-key": config.AZ_OPENAI_KEY}
        
        app_globals.ws_instance_global = websocket.WebSocketApp(
            config.WS_URL,
            header=ws_header,
            on_open=on_ws_open_new,
            on_message=on_ws_message_new,
            on_error=on_ws_error_new,  # Changed from on_ws_error to on_error
            on_close=on_ws_close_new
        )
        ws_thread = threading.Thread(target=app_globals.ws_instance_global.run_forever, daemon=True)
        ws_thread.start()

    # --- Main Loop ---
    try:
        while not app_globals.done.is_set():
            # Check if translated_speech_history contains a stop command
            stop_command = "parar gravação."
            stop_detected = False
            
            # Check the translated history list for the stop command
            with app_globals.translated_speech_history_lock:
                recent_translations = app_globals.translated_speech_history[-5:] if app_globals.translated_speech_history else []
                for trans in recent_translations:
                    if stop_command in trans.lower():
                        stop_detected = True
                        break
            
            if stop_detected:
                print(f"🏁 COMMAND: '{stop_command}' detected in translated history. Stopping...")
                app_globals.done.set()
                break
            
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n⌨️ KEYBOARD INTERRUPT: Stopping...")
        app_globals.done.set()
    finally:
        print("\n🧼 CLEANUP: Starting resource cleanup for New Dub...")
        app_globals.audio_capture_active.clear()

        if app_globals.ws_instance_global and app_globals.ws_instance_global.sock:
            app_globals.ws_instance_global.close()
        
        if ws_thread and ws_thread.is_alive():
            print("⏳ VAD WebSocket Thread: Waiting for shutdown...")
            ws_thread.join(timeout=5)
            if ws_thread.is_alive(): 
                print("⚠️ VAD WebSocket Thread: Shutdown timeout.")
            else: 
                print("✅ VAD WebSocket Thread: Shutdown complete.")
        else: 
            print("ℹ️ VAD WebSocket Thread: Already stopped or not started.")

        if stream:
            if stream.is_active():
                print("🔇 PyAudio: Stopping stream...")
                stream.stop_stream()
            print("🚪 PyAudio: Closing stream...")
            stream.close()
        print("🎧 PyAudio: Terminating...")
        p_audio.terminate()

        print("⏳ Periodic Scribe Worker: Waiting for shutdown...")
        if periodic_scribe_thread.is_alive():
            periodic_scribe_thread.join(timeout=5)
            if periodic_scribe_thread.is_alive(): 
                print("⚠️ Periodic Scribe Worker: Shutdown timeout.")
            else: 
                print("✅ Periodic Scribe Worker: Shutdown complete.")
        else: 
            print("ℹ️ Periodic Scribe Worker: Already stopped.")

        print("⏳ Translator LLM Agent Worker: Signaling and waiting for shutdown...")
        app_globals.scribe_to_translator_llm_queue.put(None)
        if translator_agent_thread.is_alive():
            translator_agent_thread.join(timeout=10)
            if translator_agent_thread.is_alive(): 
                print("⚠️ Translator LLM Agent Worker: Shutdown timeout.")
            else: 
                print("✅ Translator LLM Agent Worker: Shutdown complete.")
        else: 
            print("ℹ️ Translator LLM Agent Worker: Already stopped.")
        
        print("\n📜 Final Native Speech History (Processed by LLM):")
        print("\n".join(app_globals.native_speech_history_processed_by_llm))
        print("\n🗣️ Final Translated Speech History:")
        print("\n".join(app_globals.translated_speech_history))

        if app_globals.all_scribe_transcriptions_log:
            print("\n🎙️ All Scribe Transcriptions Logged:")
            for i, line in enumerate(app_globals.all_scribe_transcriptions_log):
                print(f"{i+1}: {line}")
        
        print("\n✅ CLEANUP: New Dub Complete. Exiting.")

if __name__ == "__main__":
    main_new_dub()
