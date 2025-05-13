"""Main application window for the Live Dubbing Application."""

import customtkinter
import tkinter as tk
import threading
import time
import pyaudio
import pygame
import pygame._sdl2.audio as sdl2_audio
import os
import sys

# Ensure parent directory is in sys.path for module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import config as config
import config_loader
import config_operations
import globals as app_globals
from workers import (
    periodic_scribe_transcription_worker_new,
    translator_llm_agent_worker_new,
    tts_worker_new,
    playback_worker_new
)
from audio_utils import pyaudio_callback_new
from websocket_handler import (
    on_ws_open_new,
    on_ws_message_new,
    on_ws_error_new,
    on_ws_close_new
)
import websocket  # For WebSocketApp type hint

from .config_window import ConfigWindow

class App(customtkinter.CTk):
    """Main application window for the Live Dubbing Application."""
    
    def __init__(self):
        super().__init__()

        self.title("Live Dubbing Application")
        self.geometry("800x700")

        app_globals.gui_app_instance = self # Make GUI instance globally available for updates

        self.core_logic_thread = None
        self.p_audio = None
        self.stream = None
        self.ws_thread = None
        self.config_window = None

        # --- UI Variables ---
        self.input_language_var = tk.StringVar(value="English")
        self.output_language_var = tk.StringVar(value="Portuguese")
        self.input_device_var = tk.StringVar(value="Default")
        self.output_device_var = tk.StringVar(value="Default")
        
        self.speaking_status_var = tk.StringVar(value="Status: Idle")
        self.transcription_text_var = tk.StringVar(value="")
        self.translation_text_var = tk.StringVar(value="")

        # --- Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # Text areas row

        self._setup_controls_frame()
        self._setup_status_action_frame()
        self._setup_text_areas_frame()
        
        self.populate_audio_devices()

        # Initialize the language dropdowns from config
        self.load_language_settings()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _setup_controls_frame(self):
        """Setup the controls frame with language and device selectors."""
        self.controls_frame = customtkinter.CTkFrame(self)
        self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.controls_frame.grid_columnconfigure((0,1,2,3), weight=1)

        # Input Language
        customtkinter.CTkLabel(self.controls_frame, text="Input Language:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.input_lang_combo = customtkinter.CTkComboBox(
            self.controls_frame, 
            variable=self.input_language_var, 
            values=["English", "Portuguese"],
            command=self.on_input_language_change  # Add command to handle changes
        )
        self.input_lang_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Output Language
        customtkinter.CTkLabel(self.controls_frame, text="Output Language:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.output_lang_combo = customtkinter.CTkComboBox(
            self.controls_frame, 
            variable=self.output_language_var, 
            values=["Portuguese", "English"],
            command=self.on_output_language_change  # Add command to handle changes
        )
        self.output_lang_combo.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        # Voice Selection
        customtkinter.CTkLabel(self.controls_frame, text="Voice:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.voice_var = tk.StringVar(value="Marcos")
        self.voice_mapping = {
            "Marcos": "CwhRBWXzGAHq8TQ4Fs17"
        }
        self.voice_combo = customtkinter.CTkComboBox(
            self.controls_frame,
            variable=self.voice_var,
            values=list(self.voice_mapping.keys()),
            command=self.on_voice_change
        )
        self.voice_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Input Device
        customtkinter.CTkLabel(self.controls_frame, text="Input Device (Mic):").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.input_device_combo = customtkinter.CTkComboBox(self.controls_frame, variable=self.input_device_var, command=self.on_input_device_change)
        self.input_device_combo.grid(row=1, column=3, padx=5, pady=5, sticky="ew")

        # Output Device
        customtkinter.CTkLabel(self.controls_frame, text="Output Device (Speaker):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.output_device_combo = customtkinter.CTkComboBox(self.controls_frame, variable=self.output_device_var, command=self.on_output_device_change)
        self.output_device_combo.grid(row=2, column=1, columnspan=3, padx=5, pady=5, sticky="ew")

        # TTS Output Toggle
        self.tts_output_var = tk.BooleanVar(value=config.TTS_OUTPUT_ENABLED)
        self.tts_output_cb = customtkinter.CTkCheckBox(
            self.controls_frame, text="Enable TTS Output", 
            variable=self.tts_output_var, command=self.on_tts_output_change
        )
        self.tts_output_cb.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="w")

    def _setup_status_action_frame(self):
        """Setup the status and action buttons frame."""
        self.status_action_frame = customtkinter.CTkFrame(self)
        self.status_action_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.status_action_frame.grid_columnconfigure((1, 2), weight=1)

        self.start_button = customtkinter.CTkButton(self.status_action_frame, text="Start Dubbing", command=self.start_translation_session)
        self.start_button.grid(row=0, column=0, padx=5, pady=5)

        self.stop_button = customtkinter.CTkButton(self.status_action_frame, text="Stop Dubbing", command=self.stop_translation_session, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=5, pady=5)
        
        self.config_button = customtkinter.CTkButton(self.status_action_frame, text="Settings", command=self.open_config_window)
        self.config_button.grid(row=0, column=2, padx=5, pady=5)
        
        self.speaking_status_label = customtkinter.CTkLabel(self.status_action_frame, textvariable=self.speaking_status_var)
        self.speaking_status_label.grid(row=0, column=3, padx=10, pady=5, sticky="e")

    def _setup_text_areas_frame(self):
        """Setup the text areas frame for transcription and translation display."""
        self.text_areas_frame = customtkinter.CTkFrame(self)
        self.text_areas_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        self.text_areas_frame.grid_columnconfigure(0, weight=1)
        self.text_areas_frame.grid_rowconfigure(1, weight=1) # Transcription textbox
        self.text_areas_frame.grid_rowconfigure(3, weight=1) # Translation textbox

        customtkinter.CTkLabel(self.text_areas_frame, text="Live Transcription (Heard):").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.transcription_textbox = customtkinter.CTkTextbox(self.text_areas_frame, height=150, state="disabled")
        self.transcription_textbox.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        customtkinter.CTkLabel(self.text_areas_frame, text="Live Translation (Spoken):").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.translation_textbox = customtkinter.CTkTextbox(self.text_areas_frame, height=150, state="disabled")
        self.translation_textbox.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")

    def open_config_window(self):
        """Open the configuration window."""
        if self.config_window is None or not self.config_window.winfo_exists():
            self.config_window = ConfigWindow(self)
            self.config_window.focus_force()  # Focus the new window
        else:
            self.config_window.focus_force()  # Focus existing window

    def load_language_settings(self):
        """Load language settings from config."""
        # Set input language dropdown
        if config.INPUT_LANGUAGE_NAME_FOR_PROMPT in ["English", "Portuguese"]:
            self.input_language_var.set(config.INPUT_LANGUAGE_NAME_FOR_PROMPT)
        
        # Set output language dropdown
        if config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT in ["English", "Portuguese"]:
            self.output_language_var.set(config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT)
            
        # Set TTS output checkbox
        self.tts_output_var.set(config.TTS_OUTPUT_ENABLED)
        
        # Set voice dropdown
        voice_id = config.ELEVENLABS_VOICE_ID
        for name, id in self.voice_mapping.items():
            if id == voice_id:
                self.voice_var.set(name)
                break

    def _get_pygame_output_devices(self) -> tuple[str, ...]:
        """Get available output devices from Pygame."""
        init_by_me = not pygame.mixer.get_init()
        if init_by_me:
            try: pygame.mixer.init()
            except Exception: 
                try: 
                    pygame.init()
                    if not pygame.mixer.get_init(): pygame.mixer.init()
                except Exception as e:
                    print(f"PYGAME_DEVICE_LIST_ERROR: {e}")
                    return tuple()
        devices = tuple(sdl2_audio.get_audio_device_names(False))
        if init_by_me and pygame.mixer.get_init(): pygame.mixer.quit()
        return devices

    def populate_audio_devices(self):
        """Populate input and output device dropdowns."""
        # Input devices (PyAudio)
        pa = pyaudio.PyAudio()
        input_devices = ["Default"]
        self.input_device_map = {"Default": None}
        try:
            default_info = pa.get_default_input_device_info()
            self.input_device_map["Default"] = default_info['index']

            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get('maxInputChannels', 0) > 0:
                    device_name = f"{info['name']} (Index {i})"
                    input_devices.append(device_name)
                    self.input_device_map[device_name] = i
        except Exception as e:
            print(f"Error populating input devices: {e}")
        finally:
            pa.terminate()
        self.input_device_combo.configure(values=input_devices)
        self.input_device_var.set(input_devices[0] if input_devices else "No devices found")

        # Output devices (Pygame/SDL2)
        output_devices = ["Default"]
        self.output_device_map = {"Default": None}
        try:
            pygame_devices = self._get_pygame_output_devices()
            if pygame_devices:
                for device_name in pygame_devices:
                    output_devices.append(device_name)
                    self.output_device_map[device_name] = device_name # Store the name itself
        except Exception as e:
            print(f"Error populating output devices: {e}")
        self.output_device_combo.configure(values=output_devices)
        self.output_device_var.set(output_devices[0] if output_devices else "No devices found")

    def on_input_language_change(self, choice):
        """Handle input language selection change."""
        if choice == "English":
            config.INPUT_LANGUAGE_NAME_FOR_PROMPT = "English"
            config.SCRIBE_LANGUAGE_CODE = "en"
        elif choice == "Portuguese":
            config.INPUT_LANGUAGE_NAME_FOR_PROMPT = "Portuguese"
            config.SCRIBE_LANGUAGE_CODE = "pt"
        
        print(f"GUI: Input Language Changed: {choice}")
        self.save_current_settings_to_config()
    
    def on_output_language_change(self, choice):
        """Handle output language selection change."""
        if choice == "English":
            config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT = "English"
        elif choice == "Portuguese":
            config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT = "Portuguese"
        
        print(f"GUI: Output Language Changed: {choice}")
        self.save_current_settings_to_config()

    def on_input_device_change(self, choice):
        """Handle input device selection change."""
        config.PYAUDIO_INPUT_DEVICE_INDEX = self.input_device_map.get(choice)
        print(f"GUI: Selected Input Device: {choice} -> Index {config.PYAUDIO_INPUT_DEVICE_INDEX}")
        self.save_current_settings_to_config()

    def on_output_device_change(self, choice):
        """Handle output device selection change."""
        config.PYAUDIO_OUTPUT_DEVICE_NAME = self.output_device_map.get(choice)
        print(f"GUI: Selected Output Device: {choice} -> Name {config.PYAUDIO_OUTPUT_DEVICE_NAME}")
        # Re-initialize pygame mixer if it was already initialized, to use new device
        if app_globals.pygame_mixer_initialized.is_set():
            pygame.mixer.quit()
            app_globals.pygame_mixer_initialized.clear()
            # The core logic will re-initialize it when needed
            print("GUI: Pygame mixer will re-initialize with new device on next playback.")
        self.save_current_settings_to_config()
    
    def on_tts_output_change(self):
        """Handle TTS output toggle change."""
        config.TTS_OUTPUT_ENABLED = self.tts_output_var.get()
        print(f"GUI: TTS Output Enabled: {config.TTS_OUTPUT_ENABLED}")
        self.save_current_settings_to_config()
    
    def on_voice_change(self, choice):
        """Handle voice selection change."""
        voice_id = self.voice_mapping.get(choice, config.DEFAULT_VOICE_ID)
        config.ELEVENLABS_VOICE_ID = voice_id
        print(f"GUI: Voice Changed: {choice} -> ID {voice_id}")
        self.save_current_settings_to_config()

    def save_current_settings_to_config(self):
        """Save current GUI settings to app_config.json."""
        app_config = config_loader.load_app_config()
        
        # Language settings
        app_config["INPUT_LANGUAGE_NAME_FOR_PROMPT"] = config.INPUT_LANGUAGE_NAME_FOR_PROMPT
        app_config["OUTPUT_LANGUAGE_NAME_FOR_PROMPT"] = config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT
        app_config["SCRIBE_LANGUAGE_CODE"] = config.SCRIBE_LANGUAGE_CODE
        
        # TTS setting
        app_config["TTS_OUTPUT_ENABLED"] = config.TTS_OUTPUT_ENABLED
        
        # Voice setting
        app_config["ELEVENLABS_VOICE_ID"] = config.ELEVENLABS_VOICE_ID
        
        # Device settings
        app_config["PYAUDIO_INPUT_DEVICE_INDEX"] = config.PYAUDIO_INPUT_DEVICE_INDEX
        app_config["PYAUDIO_OUTPUT_DEVICE_NAME"] = config.PYAUDIO_OUTPUT_DEVICE_NAME
        
        # Save to file
        config_loader.save_app_config(app_config)
        print("GUI: Settings saved to app_config.json")

    def update_speaking_status(self, is_speaking: bool):
        """Update the speaking status indicator."""
        status = "Status: Speaking..." if is_speaking else "Status: Idle"
        self.speaking_status_var.set(status)
        self.speaking_status_label.configure(text_color="green" if is_speaking else "gray")

    def update_transcription(self, text: str):
        """Update the transcription text display."""
        if text:
            self.transcription_textbox.configure(state="normal")
            current_content = self.transcription_textbox.get("1.0", tk.END).strip()
            if current_content:
                self.transcription_textbox.insert(tk.END, f"\n{text}")
            else:
                self.transcription_textbox.insert(tk.END, text)
            self.transcription_textbox.see(tk.END) # Scroll to end
            self.transcription_textbox.configure(state="disabled")

    def update_translation(self, text: str):
        """Update the translation text display."""
        if text:
            self.translation_textbox.configure(state="normal")
            current_content = self.translation_textbox.get("1.0", tk.END).strip()
            if current_content:
                self.translation_textbox.insert(tk.END, f"\n{text}")
            else:
                self.translation_textbox.insert(tk.END, text)
            self.translation_textbox.see(tk.END) # Scroll to end
            self.translation_textbox.configure(state="disabled")

    def apply_config_from_gui(self):
        """Apply current GUI settings to the config."""
        # Languages
        in_lang = self.input_language_var.get()
        out_lang = self.output_language_var.get()

        if in_lang == "English":
            config.INPUT_LANGUAGE_NAME_FOR_PROMPT = "English"
            config.SCRIBE_LANGUAGE_CODE = "en"
        elif in_lang == "Portuguese":
            config.INPUT_LANGUAGE_NAME_FOR_PROMPT = "Portuguese"
            config.SCRIBE_LANGUAGE_CODE = "pt"
        
        if out_lang == "English":
            config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT = "English"
        elif out_lang == "Portuguese":
            config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT = "Portuguese"
        
        print(f"GUI: Config Applied - Input Lang: {config.INPUT_LANGUAGE_NAME_FOR_PROMPT} ({config.SCRIBE_LANGUAGE_CODE}), Output Lang: {config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT}")
        
        # Save all current settings to config file
        self.save_current_settings_to_config()
        
        # Devices (already set by on_..._change methods, but ensure they are current)
        config.PYAUDIO_INPUT_DEVICE_INDEX = self.input_device_map.get(self.input_device_var.get())
        config.PYAUDIO_OUTPUT_DEVICE_NAME = self.output_device_map.get(self.output_device_var.get())
        print(f"GUI: Config Applied - Input Device Index: {config.PYAUDIO_INPUT_DEVICE_INDEX}, Output Device Name: {config.PYAUDIO_OUTPUT_DEVICE_NAME}")

    def start_translation_session(self):
        """Start the translation session."""
        print("GUI: Start button clicked")
        self.apply_config_from_gui()

        if not config.AZ_OPENAI_ENDPOINT or not config.AZ_OPENAI_KEY:
            self.update_speaking_status(False)
            self.speaking_status_var.set("Error: Azure credentials missing!")
            print("❌ CRITICAL: Azure OpenAI endpoint or key not configured.")
            return
        if not config.ELEVENLABS_API_KEY:
            self.update_speaking_status(False)
            self.speaking_status_var.set("Error: ElevenLabs API key missing!")
            print("❌ CRITICAL: ElevenLabs API key not configured.")
            return

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.input_lang_combo.configure(state="disabled")
        self.output_lang_combo.configure(state="disabled")
        self.input_device_combo.configure(state="disabled")
        self.output_device_combo.configure(state="disabled")
        self.config_button.configure(state="disabled")
        
        self.transcription_textbox.configure(state="normal")
        self.transcription_textbox.delete("1.0", tk.END)
        self.transcription_textbox.configure(state="disabled")
        
        self.translation_textbox.configure(state="normal")
        self.translation_textbox.delete("1.0", tk.END)
        self.translation_textbox.configure(state="disabled")

        app_globals.done.clear()
        app_globals.audio_capture_active.set()
        # Reset histories and segment ID
        app_globals.translated_speech_history.clear()
        app_globals.native_speech_history_processed_by_llm.clear()
        app_globals.all_scribe_transcriptions_log.clear()
        app_globals.next_segment_id = 0
        
        # Ensure queues are empty for a new session
        while not app_globals.scribe_to_translator_llm_queue.empty(): app_globals.scribe_to_translator_llm_queue.get()
        while not app_globals.llm_to_tts_queue.empty(): app_globals.llm_to_tts_queue.get()
        while not app_globals.tts_to_playback_queue.empty(): app_globals.tts_to_playback_queue.get()

        self.core_logic_thread = threading.Thread(target=self._run_core_logic, daemon=True)
        self.core_logic_thread.start()
        self.update_speaking_status(False) # Initial status

    def _run_core_logic(self):
        """Core logic thread function that runs the main processing pipeline."""
        print("GUI Core Logic Thread: Started")
        # Initialize Pygame mixer with selected device (or default)
        app_globals.initialize_pygame_mixer_if_needed()

        # --- Start Worker Threads ---
        print("🧵 Starting worker threads from GUI...")
        self.periodic_scribe_thread = threading.Thread(target=periodic_scribe_transcription_worker_new, daemon=True)
        self.periodic_scribe_thread.start()

        self.translator_agent_thread = threading.Thread(target=translator_llm_agent_worker_new, daemon=True)
        self.translator_agent_thread.start()

        self.tts_thread = threading.Thread(target=tts_worker_new, daemon=True)
        self.tts_thread.start()

        self.playback_thread = threading.Thread(target=playback_worker_new, daemon=True)
        self.playback_thread.start()

        # --- PyAudio Setup ---
        self.p_audio = pyaudio.PyAudio()
        try:
            print(f"Attempting to open PyAudio stream with device index: {config.PYAUDIO_INPUT_DEVICE_INDEX}")
            self.stream = self.p_audio.open(
                format=config.PYAUDIO_FORMAT,
                channels=config.PYAUDIO_CHANNELS,
                rate=config.PYAUDIO_RATE,
                input=True,
                input_device_index=config.PYAUDIO_INPUT_DEVICE_INDEX,
                frames_per_buffer=config.PYAUDIO_FRAMES_PER_BUFFER,
                stream_callback=pyaudio_callback_new
            )
            self.stream.start_stream()
            print("🎤 PyAudio Stream Started via GUI.")
        except Exception as e:
            print(f"❌ PYAUDIO_ERROR (GUI): Failed to open or start stream: {e}")
            app_globals.schedule_gui_update("speaking_status_text", f"Error: PyAudio failed: {e}")
            app_globals.done.set() # Signal stop

        # --- WebSocket Setup ---
        if not app_globals.done.is_set():
            print(f"🔌 Connecting to WebSocket via GUI: {config.WS_URL}")
            ws_header = {"api-key": config.AZ_OPENAI_KEY}
            
            app_globals.ws_instance_global = websocket.WebSocketApp(
                config.WS_URL,
                header=ws_header,
                on_open=on_ws_open_new,
                on_message=on_ws_message_new,
                on_error=on_ws_error_new,
                on_ws_close=on_ws_close_new # This will set app_globals.done on close
            )
            self.ws_thread = threading.Thread(target=app_globals.ws_instance_global.run_forever, daemon=True)
            self.ws_thread.start()

        # --- Core Loop (monitor done flag) ---
        try:
            while not app_globals.done.is_set():
                time.sleep(0.5)
        except Exception as e:
            print(f"Error in GUI core logic loop: {e}")
        finally:
            print("\n🧼 GUI Core Logic: Starting resource cleanup...")
            self._cleanup_resources()
            print("GUI Core Logic Thread: Finished")
            # Schedule GUI elements to be re-enabled on the main thread
            if app_globals.gui_app_instance:
                app_globals.gui_app_instance.after(0, self.reset_gui_after_stop)

    def _cleanup_resources(self):
        """Clean up resources when stopping the translation session."""
        app_globals.audio_capture_active.clear()

        if app_globals.ws_instance_global and app_globals.ws_instance_global.sock:
            print("GUI: Closing WebSocket...")
            app_globals.ws_instance_global.close()
        
        if self.ws_thread and self.ws_thread.is_alive():
            print("⏳ GUI: VAD WebSocket Thread: Waiting for shutdown...")
            self.ws_thread.join(timeout=2) # Shorter timeout for GUI
            if self.ws_thread.is_alive(): print("⚠️ GUI: VAD WebSocket Thread: Shutdown timeout.")
            else: print("✅ GUI: VAD WebSocket Thread: Shutdown complete.")

        if self.stream:
            if self.stream.is_active():
                print("🔇 GUI: PyAudio: Stopping stream...")
                self.stream.stop_stream()
            print("🚪 GUI: PyAudio: Closing stream...")
            self.stream.close()
        if self.p_audio:
            print("🎧 GUI: PyAudio: Terminating...")
            self.p_audio.terminate()
            self.p_audio = None
            self.stream = None

        # Signal worker threads to stop by putting None in their input queues
        print("⏳ GUI: Signaling worker threads for shutdown...")
        app_globals.scribe_to_translator_llm_queue.put(None) 

        threads_to_join = [
            (self.periodic_scribe_thread, "Periodic Scribe"),
            (self.translator_agent_thread, "Translator LLM Agent"),
            (self.tts_thread, "TTS Worker"),
            (self.playback_thread, "Playback Worker")
        ]

        for thread, name in threads_to_join:
            if thread and thread.is_alive():
                print(f"⏳ GUI: {name} Worker: Waiting for shutdown...")
                thread.join(timeout=5)
                if thread.is_alive(): print(f"⚠️ GUI: {name} Worker: Shutdown timeout.")
                else: print(f"✅ GUI: {name} Worker: Shutdown complete.")
            else: print(f"ℹ️ GUI: {name} Worker: Already stopped or not started.")

    def stop_translation_session(self):
        """Stop the translation session."""
        print("GUI: Stop button clicked")
        app_globals.done.set() # Signal all threads and loops to stop

    def reset_gui_after_stop(self):
        """Reset the GUI state after stopping a translation session."""
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.input_lang_combo.configure(state="normal")
        self.output_lang_combo.configure(state="normal")
        self.input_device_combo.configure(state="normal")
        self.output_device_combo.configure(state="normal")
        self.config_button.configure(state="normal")
        self.update_speaking_status(False)
        self.speaking_status_var.set("Status: Stopped")
        print("GUI: Interface reset after stop.")

    def on_closing(self):
        """Handle window close event."""
        print("GUI: Closing application window...")
        if self.core_logic_thread and self.core_logic_thread.is_alive():
            print("GUI: Signaling core logic to stop due to window close...")
            app_globals.done.set()
            self.core_logic_thread.join(timeout=10) # Wait for core logic to clean up
            if self.core_logic_thread.is_alive():
                print("⚠️ GUI: Core logic thread did not stop in time during window close.")
        
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        pygame.quit()
        self.destroy()


if __name__ == '__main__':
    # This is for testing the GUI independently if needed.
    # The main application will run it via main.py
    customtkinter.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
    customtkinter.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"
    app = App()
    app.mainloop()
