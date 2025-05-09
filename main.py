import threading
import time
import pyaudio
import websocket
import pygame # For pygame.quit()

# Import from the live-dub-test package
from live_dub_test import config
from live_dub_test import globals as app_globals # aliasing to avoid conflict if main also has 'globals'
from live_dub_test.workers import (
    translation_worker_thread_func,
    audio_generation_worker_thread_func,
    playback_worker_thread_func,
    periodic_transcription_thread_func
)
from live_dub_test.audio_processing import pyaudio_callback
from live_dub_test.websocket_handler import (
    on_ws_open,
    on_ws_message,
    on_ws_error,
    on_ws_close
)
from live_dub_test.device_selector import select_audio_devices

def main():
    # 1) Seleção interativa de dispositivos
    select_audio_devices()

    # --- Initialize Pygame Mixer (default device) ---
    app_globals.initialize_pygame_mixer()

    # Start worker threads
    translation_thread = threading.Thread(target=translation_worker_thread_func, daemon=True)
    translation_thread.start()

    audio_generation_thread = threading.Thread(target=audio_generation_worker_thread_func, daemon=True)
    audio_generation_thread.start()

    playback_thread = threading.Thread(target=playback_worker_thread_func, daemon=True)
    playback_thread.start()

    periodic_thread = threading.Thread(target=periodic_transcription_thread_func, daemon=True)
    periodic_thread.start()

    # PyAudio setup
    p_audio = pyaudio.PyAudio()
    stream = None
    try:
        stream = p_audio.open(format=config.PYAUDIO_FORMAT,
                              channels=config.PYAUDIO_CHANNELS,
                              rate=config.PYAUDIO_RATE,
                              input=True,
                              input_device_index=config.PYAUDIO_INPUT_DEVICE_INDEX,   # <--- adicionado
                              frames_per_buffer=config.PYAUDIO_FRAMES_PER_BUFFER,
                              stream_callback=pyaudio_callback)
        stream.start_stream()
        print("🎤 PyAudio Stream Started.")
    except Exception as e:
        print(f"❌ PYAUDIO_ERROR: Failed to open or start stream: {e}")
        app_globals.done = True # Signal shutdown if audio input fails

    # WebSocket setup
    ws_thread = None
    if not app_globals.done: # Only proceed if PyAudio setup was okay
        print(f"🔌 Connecting to WebSocket: {config.WS_URL}")
        ws_header = {"api-key": config.AZ_OPENAI_KEY}
        
        # Assign to globals.ws_instance_global so it can be accessed for closing
        app_globals.ws_instance_global = websocket.WebSocketApp(config.WS_URL,
                                                        header=ws_header,
                                                        on_open=on_ws_open,
                                                        on_message=on_ws_message,
                                                        on_error=on_ws_error,
                                                        on_close=on_ws_close)
        ws_thread = threading.Thread(target=app_globals.ws_instance_global.run_forever, daemon=True)
        ws_thread.start()

    # Main loop
    try:
        while not app_globals.done:
            # Check for stop command from translated text
            if app_globals.all_results and app_globals.all_results[-1] and \
               app_globals.all_results[-1].strip().lower() == "parar gravação.": # Example stop command
                print("🏁 COMMAND: 'parar gravação.' detected. Stopping...")
                if app_globals.ws_instance_global and app_globals.ws_instance_global.sock:
                    app_globals.ws_instance_global.close()
                else: # If WS already closed or failed to start
                    app_globals.done = True 
                app_globals.audio_capture_active.clear() # Stop PyAudio callback from processing
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n⌨️ KEYBOARD INTERRUPT: Stopping...")
        if not app_globals.done:
            if app_globals.ws_instance_global and app_globals.ws_instance_global.sock:
                app_globals.ws_instance_global.close() # This will trigger on_ws_close, setting app_globals.done
            else:
                app_globals.done = True
            app_globals.audio_capture_active.clear()
    finally:
        print("\n🧼 CLEANUP: Starting resource cleanup...")
        app_globals.audio_capture_active.clear() # Ensure audio capture is stopped

        if not app_globals.done: # If not already set by WS close or command
            print("🧼 CLEANUP: Ensuring WebSocket is closed (if running).")
            if app_globals.ws_instance_global and app_globals.ws_instance_global.sock:
                app_globals.ws_instance_global.close()
            app_globals.done = True # Explicitly set done for all threads

        if ws_thread and ws_thread.is_alive():
            print("⏳ WebSocket Thread: Waiting for shutdown...")
            ws_thread.join(timeout=5)
            if ws_thread.is_alive(): print("⚠️ WebSocket Thread: Shutdown timeout.")
            else: print("✅ WebSocket Thread: Shutdown complete.")
        else: print("ℹ️ WebSocket Thread: Already stopped or not started.")

        if stream:
            if stream.is_active():
                print("🔇 PyAudio: Stopping stream...")
                stream.stop_stream()
            print("🚪 PyAudio: Closing stream...")
            stream.close()
        print("🎧 PyAudio: Terminating...")
        p_audio.terminate()

        # Signal worker threads to stop by putting None in their queues
        # (already handled by `done` flag and queue timeouts, but explicit None is cleaner)
        # Note: translation_worker_thread_func already puts None to text_to_speech_queue
        # and audio_generation_worker_thread_func puts None to audio_bytes_to_playback_queue
        # when they receive None.
        # We just need to ensure the first queue in the chain gets a None if not already done.
        
        print("⏳ Periodic Transcription Worker: Signaling for shutdown (via 'done' flag)...")
        # periodic_thread doesn't use a queue, relies on app_globals.done
        if periodic_thread.is_alive():
            print("⏳ Periodic Transcription Worker: Waiting for shutdown...")
            periodic_thread.join(timeout=5) # Give it time to see 'done' flag
            if periodic_thread.is_alive(): print("⚠️ Periodic Transcription Worker: Shutdown timeout.")
            else: print("✅ Periodic Transcription Worker: Shutdown complete.")
        else: print("ℹ️ Periodic Transcription Worker: Already stopped.")

        print("⏳ Translation Worker: Signaling for shutdown...")
        app_globals.transcription_to_translation_queue.put(None) # Signal translation worker
        if translation_thread.is_alive():
            print("⏳ Translation Worker: Waiting for shutdown...")
            translation_thread.join(timeout=10)
            if translation_thread.is_alive(): print("⚠️ Translation Worker: Shutdown timeout.")
            else: print("✅ Translation Worker: Shutdown complete.")
        else: print("ℹ️ Translation Worker: Already stopped.")
        
        # Audio generation and playback threads are signaled by the preceding thread in the queue chain.
        # We join them to ensure they finish.
        if audio_generation_thread.is_alive():
            print("⏳ Audio Generation Worker: Waiting for shutdown...")
            audio_generation_thread.join(timeout=10)
            if audio_generation_thread.is_alive(): print("⚠️ Audio Generation Worker: Shutdown timeout.")
            else: print("✅ Audio Generation Worker: Shutdown complete.")
        else: print("ℹ️ Audio Generation Worker: Already stopped.")

        if playback_thread.is_alive():
            print("⏳ Playback Worker: Waiting for shutdown...")
            playback_thread.join(timeout=10)
            if playback_thread.is_alive(): print("⚠️ Playback Worker: Shutdown timeout.")
            else: print("✅ Playback Worker: Shutdown complete.")
        else: print("ℹ️ Playback Worker: Already stopped.")
        
        if pygame.mixer.get_init():
            pygame.mixer.quit()
            print("🎮 Pygame Mixer: Quit.")
        pygame.quit() # Quit all pygame modules
        print("✅ CLEANUP: Complete. Exiting.")

if __name__ == "__main__":
    main()
