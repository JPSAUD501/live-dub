import threading
import time
import pyaudio
import websocket
import os
import sys
import pygame
import pygame._sdl2.audio as sdl2_audio  # For listing output devices

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
        translator_llm_agent_worker_new,
        tts_worker_new,
        playback_worker_new
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
        translator_llm_agent_worker_new,
        tts_worker_new,
        playback_worker_new
    )
    from .audio_utils_new import pyaudio_callback_new
    from .websocket_handler_new import (
        on_ws_open_new,
        on_ws_message_new,
        on_ws_error_new,
        on_ws_close_new
    )

def get_pygame_output_devices() -> tuple[str, ...]:
    # Helper function to get output device names from Pygame/SDL2
    # Temporarily init mixer if not already initialized to query devices
    init_by_me = not pygame.mixer.get_init()
    if init_by_me:
        try:
            pygame.mixer.init()
        except pygame.error:  # Fallback if default init fails
            try:
                pygame.init()  # Try full pygame init
                if not pygame.mixer.get_init():  # Check again
                    pygame.mixer.init()
            except Exception as e:
                print(f"⚠️ PYGAME_DEVICE_LIST_ERROR: Could not init mixer/pygame to list devices: {e}")
                return tuple()  # Return empty tuple if init fails

    devices = tuple(sdl2_audio.get_audio_device_names(False))  # False for playback devices
    
    if init_by_me and pygame.mixer.get_init():  # Quit only if we initialized it and it's still init
        pygame.mixer.quit()
    return devices

def select_audio_devices_interactive():
    """Interactive selection for input (PyAudio) and output (Pygame) devices."""
    p = pyaudio.PyAudio()
    
    # --- Input Device Selection (PyAudio) ---
    print("\n=== Available Input Devices (PyAudio) ===")
    input_devices_info = []
    default_input_device_info = p.get_default_input_device_info()
    print(f"Default Input: #{default_input_device_info['index']} - {default_input_device_info['name']}")

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info.get('maxInputChannels', 0) > 0:
            input_devices_info.append({'index': i, 'name': info['name']})
            print(f"{i}: {info['name']}")
    
    selected_input_idx_str = input(f"Select Input Device [PyAudio index, default: {default_input_device_info['index']}]: ")
    try:
        if not selected_input_idx_str.strip():
            idx_in = default_input_device_info['index']
            print(f"Using default input device: #{idx_in} - {default_input_device_info['name']}")
        else:
            idx_in = int(selected_input_idx_str)
            if not any(dev['index'] == idx_in for dev in input_devices_info):
                print(f"Invalid input device index: {idx_in}. Using default.")
                idx_in = default_input_device_info['index']
        config.PYAUDIO_INPUT_DEVICE_INDEX = idx_in
        selected_input_name = p.get_device_info_by_index(idx_in)['name']
        print(f"🎤 Input device selected: #{idx_in} - {selected_input_name}")
    except ValueError:
        print(f"Invalid input: '{selected_input_idx_str}'. Using default input device.")
        config.PYAUDIO_INPUT_DEVICE_INDEX = default_input_device_info['index']
        print(f"🎤 Input device selected: #{config.PYAUDIO_INPUT_DEVICE_INDEX} - {default_input_device_info['name']}")
    
    p.terminate()

    # --- Output Device Selection (Pygame/SDL2) ---
    print("\n=== Available Output Devices (Pygame/SDL2) ===")
    output_device_names_pygame = get_pygame_output_devices()
    
    default_output_device_name = None
    if output_device_names_pygame:  # Pygame doesn't have a simple "default" query like PyAudio for specific name
        default_output_device_name = output_device_names_pygame[0]  # Fallback to first if no better default
        print(f"Default Output (first available): {default_output_device_name}")
        for i, name in enumerate(output_device_names_pygame):
            print(f"{i}: {name}")
        
        selected_output_idx_str = input(f"Select Output Device [Pygame index, default: 0 ({default_output_device_name})]: ")
        try:
            if not selected_output_idx_str.strip():
                idx_out_pygame = 0
                print(f"Using default output device (first available): {output_device_names_pygame[idx_out_pygame]}")
            else:
                idx_out_pygame = int(selected_output_idx_str)
                if not (0 <= idx_out_pygame < len(output_device_names_pygame)):
                    print(f"Invalid output device index: {idx_out_pygame}. Using first available.")
                    idx_out_pygame = 0
            config.PYAUDIO_OUTPUT_DEVICE_NAME = output_device_names_pygame[idx_out_pygame]
            print(f"🎧 Output device selected: #{idx_out_pygame} - {config.PYAUDIO_OUTPUT_DEVICE_NAME}")
        except ValueError:
            print(f"Invalid input: '{selected_output_idx_str}'. Using first available output device.")
            config.PYAUDIO_OUTPUT_DEVICE_NAME = output_device_names_pygame[0]
            print(f"🎧 Output device selected: #0 - {config.PYAUDIO_OUTPUT_DEVICE_NAME}")
    else:
        print("⚠️ No output devices found by Pygame/SDL2. Playback will use system default (if any).")
        config.PYAUDIO_OUTPUT_DEVICE_NAME = None

def main_new_dub():
    """Main function for the new_dub application"""
    print("🚀 Starting New Dub Application...")
    pygame.init()  # Initialize all Pygame modules (needed for sdl2_audio and mixer)
    
    # Select devices before initializing mixer with specific device
    select_audio_devices_interactive()

    # Now initialize mixer with potentially selected device
    app_globals.initialize_pygame_mixer_if_needed()

    if not config.AZ_OPENAI_ENDPOINT or not config.AZ_OPENAI_KEY:
        print("❌ CRITICAL: Azure OpenAI endpoint or key not configured. Cannot continue.")
        return

    if not config.ELEVENLABS_API_KEY:
        print("❌ CRITICAL: ElevenLabs API key not configured. Cannot continue.")
        return

    # --- Start Worker Threads ---
    print("🧵 Starting worker threads...")
    periodic_scribe_thread = threading.Thread(target=periodic_scribe_transcription_worker_new, daemon=True)
    periodic_scribe_thread.start()

    translator_agent_thread = threading.Thread(target=translator_llm_agent_worker_new, daemon=True)
    translator_agent_thread.start()

    tts_thread = threading.Thread(target=tts_worker_new, daemon=True)
    tts_thread.start()

    playback_thread = threading.Thread(target=playback_worker_new, daemon=True)
    playback_thread.start()

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
            on_error=on_ws_error_new,
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
        app_globals.scribe_to_translator_llm_queue.put(None)  # Signals translator_llm_agent_worker
        # translator_llm_agent_worker will signal tts_worker by putting None in llm_to_tts_queue
        # tts_worker will signal playback_worker by putting None in tts_to_playback_queue

        if translator_agent_thread.is_alive():
            translator_agent_thread.join(timeout=10)
            if translator_agent_thread.is_alive(): 
                print("⚠️ Translator LLM Agent Worker: Shutdown timeout.")
            else: 
                print("✅ Translator LLM Agent Worker: Shutdown complete.")
        else: 
            print("ℹ️ Translator LLM Agent Worker: Already stopped.")

        if tts_thread.is_alive():
            print("⏳ TTS Worker: Waiting for shutdown...")
            tts_thread.join(timeout=10)
            if tts_thread.is_alive():
                print("⚠️ TTS Worker: Shutdown timeout.")
            else:
                print("✅ TTS Worker: Shutdown complete.")
        else:
            print("ℹ️ TTS Worker: Already stopped.")

        if playback_thread.is_alive():
            print("⏳ Playback Worker: Waiting for shutdown...")
            playback_thread.join(timeout=10)
            if playback_thread.is_alive():
                print("⚠️ Playback Worker: Shutdown timeout.")
            else:
                print("✅ Playback Worker: Shutdown complete.")
        else:
            print("ℹ️ Playback Worker: Already stopped.")
        
        print("\n📜 Final Native Speech History (Processed by LLM):")
        print("\n".join(app_globals.native_speech_history_processed_by_llm))
        print("\n🗣️ Final Translated Speech History:")
        print("\n".join(app_globals.translated_speech_history))

        if app_globals.all_scribe_transcriptions_log:
            print("\n🎙️ All Scribe Transcriptions Logged:")
            for i, line in enumerate(app_globals.all_scribe_transcriptions_log):
                print(f"{i+1}: {line}")
        
        pygame.quit()  # Quit Pygame
        print("\n✅ CLEANUP: New Dub Complete. Exiting.")

if __name__ == "__main__":
    main_new_dub()
