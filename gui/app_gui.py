import customtkinter
import tkinter as tk
import threading
import time
import pyaudio
import pygame
import pygame._sdl2.audio as sdl2_audio
import os
import sys
import json

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
import websocket # For WebSocketApp type hint

customtkinter.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
customtkinter.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class ConfigWindow(customtkinter.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Configuration")
        self.geometry("600x500")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.api_config = config_loader.load_api_config()
        self.app_config = config_loader.load_app_config()
        
        # Create notebook (tabs)
        self.tabview = customtkinter.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Add tabs
        self.tabview.add("API Keys")
        self.tabview.add("Application Settings")
        
        # Create API Keys tab content
        self.create_api_keys_tab()
        
        # Create Application Settings tab content
        self.create_app_settings_tab()
        
        # Create buttons at bottom
        self.button_frame = customtkinter.CTkFrame(self)
        self.button_frame.pack(fill="x", padx=10, pady=10)
        
        self.save_button = customtkinter.CTkButton(
            self.button_frame, text="Save Changes", command=self.save_all_config
        )
        self.save_button.pack(side="right", padx=5)
        
        self.cancel_button = customtkinter.CTkButton(
            self.button_frame, text="Cancel", command=self.on_closing
        )
        self.cancel_button.pack(side="right", padx=5)

    def create_api_keys_tab(self):
        tab = self.tabview.tab("API Keys")
        
        # Azure OpenAI
        customtkinter.CTkLabel(tab, text="Azure OpenAI Endpoint:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.az_endpoint_entry = customtkinter.CTkEntry(tab, width=400)
        self.az_endpoint_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        self.az_endpoint_entry.insert(0, self.api_config.get("AZ_OPENAI_ENDPOINT", ""))
        
        customtkinter.CTkLabel(tab, text="Azure OpenAI Key:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.az_key_entry = customtkinter.CTkEntry(tab, width=400, show="*")
        self.az_key_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.az_key_entry.insert(0, self.api_config.get("AZ_OPENAI_KEY", ""))
        
        customtkinter.CTkLabel(tab, text="LLM Deployment Name:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.llm_deployment_entry = customtkinter.CTkEntry(tab, width=400)
        self.llm_deployment_entry.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        self.llm_deployment_entry.insert(0, self.api_config.get("AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME", "gpt-4o-mini"))
        
        # ElevenLabs
        customtkinter.CTkLabel(tab, text="ElevenLabs API Key:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.el_key_entry = customtkinter.CTkEntry(tab, width=400, show="*")
        self.el_key_entry.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        self.el_key_entry.insert(0, self.api_config.get("ELEVENLABS_API_KEY", ""))
        
        # Voice selection dropdown
        customtkinter.CTkLabel(tab, text="ElevenLabs Voice:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        
        # Define available voices with their IDs and names
        self.available_voices = {
            "CwhRBWXzGAHq8TQ4Fs17": "Marcos"  # Current voice as default
        }
        
        # Create the dropdown with just the name (without ID in display)
        self.voice_names = ["Marcos"]  # Just the name for display
        self.voice_id_mapping = {"Marcos": "CwhRBWXzGAHq8TQ4Fs17"}  # Map from display name to ID
        
        # Get the current voice and set the display value
        current_voice_id = self.api_config.get("ELEVENLABS_VOICE_ID", "CwhRBWXzGAHq8TQ4Fs17")
        current_voice_name = self.available_voices.get(current_voice_id, "Marcos")
        
        # Create the dropdown
        self.el_voice_var = tk.StringVar(value=current_voice_name)
        self.el_voice_combo = customtkinter.CTkComboBox(
            tab, width=400, variable=self.el_voice_var,
            values=self.voice_names
        )
        self.el_voice_combo.grid(row=4, column=1, sticky="ew", padx=10, pady=5)
        
        # Toggle show/hide password
        self.show_passwords_var = tk.BooleanVar(value=False)
        self.show_passwords_cb = customtkinter.CTkCheckBox(
            tab, text="Show passwords", variable=self.show_passwords_var, 
            command=self.toggle_password_visibility
        )
        self.show_passwords_cb.grid(row=5, column=1, sticky="w", padx=10, pady=10)
        
        # Test connections
        self.test_az_button = customtkinter.CTkButton(
            tab, text="Test Azure OpenAI Connection", 
            command=self.test_azure_connection
        )
        self.test_az_button.grid(row=6, column=0, padx=10, pady=10)
        
        self.test_el_button = customtkinter.CTkButton(
            tab, text="Test ElevenLabs Connection", 
            command=self.test_elevenlabs_connection
        )
        self.test_el_button.grid(row=6, column=1, padx=10, pady=10)

    def create_app_settings_tab(self):
        tab = self.tabview.tab("Application Settings")
        
        # Create a scrollable frame
        self.settings_frame = customtkinter.CTkScrollableFrame(tab)
        self.settings_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Language settings
        customtkinter.CTkLabel(self.settings_frame, text="Language Settings", font=("", 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))
        
        customtkinter.CTkLabel(self.settings_frame, text="Input Language:").grid(
            row=1, column=0, sticky="w", padx=10, pady=5)
        self.input_lang_var = tk.StringVar(value=self.app_config.get("INPUT_LANGUAGE_NAME_FOR_PROMPT", "English"))
        self.input_lang_combo = customtkinter.CTkComboBox(
            self.settings_frame, variable=self.input_lang_var, values=["English", "Portuguese", "Spanish", "French"])
        self.input_lang_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        customtkinter.CTkLabel(self.settings_frame, text="Output Language:").grid(
            row=2, column=0, sticky="w", padx=10, pady=5)
        self.output_lang_var = tk.StringVar(value=self.app_config.get("OUTPUT_LANGUAGE_NAME_FOR_PROMPT", "Portuguese"))
        self.output_lang_combo = customtkinter.CTkComboBox(
            self.settings_frame, variable=self.output_lang_var, values=["English", "Portuguese", "Spanish", "French"])
        self.output_lang_combo.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        
        customtkinter.CTkLabel(self.settings_frame, text="Scribe Language Code:").grid(
            row=3, column=0, sticky="w", padx=10, pady=5)
        self.scribe_lang_var = tk.StringVar(value=self.app_config.get("SCRIBE_LANGUAGE_CODE", "en"))
        self.scribe_lang_combo = customtkinter.CTkComboBox(
            self.settings_frame, variable=self.scribe_lang_var, values=["en", "pt", "es", "fr"])
        self.scribe_lang_combo.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        
        # Transcription settings
        customtkinter.CTkLabel(self.settings_frame, text="Transcription Settings", font=("", 16, "bold")).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(15, 5))
        
        customtkinter.CTkLabel(self.settings_frame, text="Periodic Transcription Interval (s):").grid(
            row=5, column=0, sticky="w", padx=10, pady=5)
        self.periodic_interval_var = tk.StringVar(value=str(self.app_config.get("PERIODIC_SCRIBE_INTERVAL_S", 3.0)))
        self.periodic_interval_entry = customtkinter.CTkEntry(self.settings_frame, textvariable=self.periodic_interval_var)
        self.periodic_interval_entry.grid(row=5, column=1, sticky="ew", padx=10, pady=5)
        
        customtkinter.CTkLabel(self.settings_frame, text="Inter-Chunk Overlap (ms):").grid(
            row=6, column=0, sticky="w", padx=10, pady=5)
        self.overlap_var = tk.StringVar(value=str(self.app_config.get("PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS", 250)))
        self.overlap_entry = customtkinter.CTkEntry(self.settings_frame, textvariable=self.overlap_var)
        self.overlap_entry.grid(row=6, column=1, sticky="ew", padx=10, pady=5)
        
        customtkinter.CTkLabel(self.settings_frame, text="Final Transcription Pre-roll (ms):").grid(
            row=7, column=0, sticky="w", padx=10, pady=5)
        self.preroll_var = tk.StringVar(value=str(self.app_config.get("FINAL_SCRIBE_PRE_ROLL_MS", 500)))
        self.preroll_entry = customtkinter.CTkEntry(self.settings_frame, textvariable=self.preroll_var)
        self.preroll_entry.grid(row=7, column=1, sticky="ew", padx=10, pady=5)
        
        # VAD Settings
        customtkinter.CTkLabel(self.settings_frame, text="Voice Activity Detection", font=("", 16, "bold")).grid(
            row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(15, 5))
        
        customtkinter.CTkLabel(self.settings_frame, text="Silence Timeout (ms):").grid(
            row=9, column=0, sticky="w", padx=10, pady=5)
        self.vad_silence_var = tk.StringVar(value=str(self.app_config.get("AZ_VAD_SILENCE_TIMEOUT_MS", 500)))
        self.vad_silence_entry = customtkinter.CTkEntry(self.settings_frame, textvariable=self.vad_silence_var)
        self.vad_silence_entry.grid(row=9, column=1, sticky="ew", padx=10, pady=5)
        
        customtkinter.CTkLabel(self.settings_frame, text="Pre-roll (ms):").grid(
            row=10, column=0, sticky="w", padx=10, pady=5)
        self.vad_preroll_var = tk.StringVar(value=str(self.app_config.get("AZ_VAD_PRE_ROLL_MS", 300)))
        self.vad_preroll_entry = customtkinter.CTkEntry(self.settings_frame, textvariable=self.vad_preroll_var)
        self.vad_preroll_entry.grid(row=10, column=1, sticky="ew", padx=10, pady=5)
        
        # LLM Context settings
        customtkinter.CTkLabel(self.settings_frame, text="LLM Context Settings", font=("", 16, "bold")).grid(
            row=11, column=0, columnspan=2, sticky="w", padx=10, pady=(15, 5))
        
        customtkinter.CTkLabel(self.settings_frame, text="Context Window Size:").grid(
            row=12, column=0, sticky="w", padx=10, pady=5)
        self.context_window_var = tk.StringVar(value=str(self.app_config.get("LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE", 5)))
        self.context_window_entry = customtkinter.CTkEntry(self.settings_frame, textvariable=self.context_window_var)
        self.context_window_entry.grid(row=12, column=1, sticky="ew", padx=10, pady=5)
        
        customtkinter.CTkLabel(self.settings_frame, text="Max Native History (chars):").grid(
            row=13, column=0, sticky="w", padx=10, pady=5)
        self.native_history_var = tk.StringVar(value=str(self.app_config.get("MAX_NATIVE_HISTORY_CHARS", 5000)))
        self.native_history_entry = customtkinter.CTkEntry(self.settings_frame, textvariable=self.native_history_var)
        self.native_history_entry.grid(row=13, column=1, sticky="ew", padx=10, pady=5)
        
        customtkinter.CTkLabel(self.settings_frame, text="Max Translated History (chars):").grid(
            row=14, column=0, sticky="w", padx=10, pady=5)
        self.translated_history_var = tk.StringVar(value=str(self.app_config.get("MAX_TRANSLATED_HISTORY_CHARS", 5000)))
        self.translated_history_entry = customtkinter.CTkEntry(self.settings_frame, textvariable=self.translated_history_var)
        self.translated_history_entry.grid(row=14, column=1, sticky="ew", padx=10, pady=5)
        
        # TTS Output Enable/Disable
        customtkinter.CTkLabel(self.settings_frame, text="TTS Output", font=("", 16, "bold")).grid(
            row=15, column=0, columnspan=2, sticky="w", padx=10, pady=(15, 5))
        
        self.tts_enabled_var = tk.BooleanVar(value=self.app_config.get("TTS_OUTPUT_ENABLED", True))
        self.tts_enabled_cb = customtkinter.CTkCheckBox(
            self.settings_frame, text="Enable TTS Output", variable=self.tts_enabled_var)
        self.tts_enabled_cb.grid(row=16, column=0, columnspan=2, sticky="w", padx=10, pady=5)
    
    def toggle_password_visibility(self):
        show_char = "" if self.show_passwords_var.get() else "*"
        self.az_key_entry.configure(show=show_char)
        self.el_key_entry.configure(show=show_char)
    
    def test_azure_connection(self):
        # Temporarily update config with current values
        temp_endpoint = self.az_endpoint_entry.get().strip()
        temp_key = self.az_key_entry.get().strip()
        temp_deployment = self.llm_deployment_entry.get().strip()
        
        if not temp_endpoint or not temp_key:
            self.show_message("Error", "Please enter both endpoint and key to test connection.")
            return
        
        # Create temporary client
        try:
            from openai import AzureOpenAI
            client = AzureOpenAI(
                api_version=config.AZ_OPENAI_API_VERSION,
                azure_endpoint=temp_endpoint,
                api_key=temp_key
            )
            
            # Test with a simple request
            response = client.chat.completions.create(
                model=temp_deployment,
                messages=[{"role": "user", "content": "Test connection. Reply with only 'Connection successful'"}],
                max_tokens=15
            )
            
            if response and response.choices:
                self.show_message("Success", "Azure OpenAI connection successful!")
            else:
                self.show_message("Warning", "Connection established but unexpected response format.")
                
        except Exception as e:
            self.show_message("Error", f"Connection failed: {str(e)}")

    def test_elevenlabs_connection(self):
        # Temporarily update config with current values
        temp_key = self.el_key_entry.get().strip()
        
        if not temp_key:
            self.show_message("Error", "Please enter ElevenLabs API key to test connection.")
            return
        
        # Create temporary client
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=temp_key)
            
            # Test with a simple request (get voices)
            voices = client.voices.get_all()
            
            if voices:
                voice_names = [v.name for v in voices]
                self.show_message("Success", f"ElevenLabs connection successful!\nAvailable voices: {', '.join(voice_names[:5])}" + 
                                 (f" and {len(voice_names)-5} more..." if len(voice_names) > 5 else ""))
            else:
                self.show_message("Warning", "Connection established but no voices found.")
                
        except Exception as e:
            self.show_message("Error", f"Connection failed: {str(e)}")
    
    def save_api_config(self):
        # Update API config from form fields
        self.api_config["AZ_OPENAI_ENDPOINT"] = self.az_endpoint_entry.get().strip()
        self.api_config["AZ_OPENAI_KEY"] = self.az_key_entry.get().strip()
        self.api_config["AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME"] = self.llm_deployment_entry.get().strip()
        self.api_config["ELEVENLABS_API_KEY"] = self.el_key_entry.get().strip()
        
        # Get the selected voice ID from the mapping
        selected_voice_name = self.el_voice_var.get()
        self.api_config["ELEVENLABS_VOICE_ID"] = self.voice_id_mapping.get(
            selected_voice_name, "CwhRBWXzGAHq8TQ4Fs17"  # Default if not found
        )
        
        # Save to file
        config_loader.save_api_config(self.api_config)
    
    def save_app_config(self):
        # Update app config from form fields
        self.app_config["INPUT_LANGUAGE_NAME_FOR_PROMPT"] = self.input_lang_var.get()
        self.app_config["OUTPUT_LANGUAGE_NAME_FOR_PROMPT"] = self.output_lang_var.get()
        self.app_config["SCRIBE_LANGUAGE_CODE"] = self.scribe_lang_var.get()
        self.app_config["TTS_OUTPUT_ENABLED"] = self.tts_enabled_var.get()
        
        # Numeric fields with validation
        try:
            self.app_config["PERIODIC_SCRIBE_INTERVAL_S"] = float(self.periodic_interval_var.get())
            self.app_config["PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS"] = int(self.overlap_var.get())
            self.app_config["FINAL_SCRIBE_PRE_ROLL_MS"] = int(self.preroll_var.get())
            self.app_config["LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE"] = int(self.context_window_var.get())
            self.app_config["MAX_NATIVE_HISTORY_CHARS"] = int(self.native_history_var.get())
            self.app_config["MAX_TRANSLATED_HISTORY_CHARS"] = int(self.translated_history_var.get())
            self.app_config["AZ_VAD_SILENCE_TIMEOUT_MS"] = int(self.vad_silence_var.get())
            self.app_config["AZ_VAD_PRE_ROLL_MS"] = int(self.vad_preroll_var.get())
        except ValueError:
            self.show_message("Error", "Some numeric fields contain invalid values. Please check and try again.")
            return False
        
        # Save to file
        config_loader.save_app_config(self.app_config)
        return True
        
    def save_all_config(self):
        self.save_api_config()
        if self.save_app_config():
            # Update the running configuration
            config_loader.update_config_module(self.api_config, self.app_config)
            
            # Re-apply config operations
            config.WS_URL = config_operations.compute_ws_url()
            config.client_az_llm = config_operations.initialize_azure_openai_client()
            config.elevenlabs_client = config_operations.initialize_elevenlabs_client()
            
            self.show_message("Success", "Configuration saved successfully!")
            self.destroy()
    
    def show_message(self, title, message):
        messagebox = customtkinter.CTkToplevel(self)
        messagebox.title(title)
        messagebox.geometry("400x200")
        messagebox.grab_set()  # Make modal
        
        # Center on parent
        window_width = 400
        window_height = 200
        position_x = self.winfo_x() + (self.winfo_width() // 2) - (window_width // 2)
        position_y = self.winfo_y() + (self.winfo_height() // 2) - (window_height // 2)
        messagebox.geometry(f"{window_width}x{window_height}+{position_x}+{position_y}")
        
        # Add content
        msg_frame = customtkinter.CTkFrame(messagebox, corner_radius=0)
        msg_frame.pack(fill="both", expand=True)
        
        msg_label = customtkinter.CTkLabel(
            msg_frame, text=message, wraplength=380, justify="left")
        msg_label.pack(padx=20, pady=20, expand=True)
        
        ok_button = customtkinter.CTkButton(
            msg_frame, text="OK", command=messagebox.destroy, width=100)
        ok_button.pack(pady=10)
        
        # Make sure we destroy the window if user clicks the X
        messagebox.protocol("WM_DELETE_WINDOW", messagebox.destroy)
    
    def on_closing(self):
        self.destroy()

class App(customtkinter.CTk):
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

        # --- Controls Frame ---
        self.controls_frame = customtkinter.CTkFrame(self)
        self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.controls_frame.grid_columnconfigure((0,1,2,3), weight=1)

        # Input Language
        customtkinter.CTkLabel(self.controls_frame, text="Input Language:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.input_lang_combo = customtkinter.CTkComboBox(self.controls_frame, variable=self.input_language_var, values=["English", "Portuguese"])
        self.input_lang_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Output Language
        customtkinter.CTkLabel(self.controls_frame, text="Output Language:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.output_lang_combo = customtkinter.CTkComboBox(self.controls_frame, variable=self.output_language_var, values=["Portuguese", "English"])
        self.output_lang_combo.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        # Input Device
        customtkinter.CTkLabel(self.controls_frame, text="Input Device (Mic):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.input_device_combo = customtkinter.CTkComboBox(self.controls_frame, variable=self.input_device_var, command=self.on_input_device_change)
        self.input_device_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Output Device
        customtkinter.CTkLabel(self.controls_frame, text="Output Device (Speaker):").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.output_device_combo = customtkinter.CTkComboBox(self.controls_frame, variable=self.output_device_var, command=self.on_output_device_change)
        self.output_device_combo.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        
        self.populate_audio_devices()

        # --- Status and Action Frame ---
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

        # --- Text Areas Frame ---
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

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def open_config_window(self):
        if self.config_window is None or not self.config_window.winfo_exists():
            self.config_window = ConfigWindow(self)
            self.config_window.focus_force()  # Focus the new window
        else:
            self.config_window.focus_force()  # Focus existing window

    def load_language_settings(self):
        """Load language settings from config"""
        # Set input language dropdown
        if config.INPUT_LANGUAGE_NAME_FOR_PROMPT in ["English", "Portuguese"]:
            self.input_language_var.set(config.INPUT_LANGUAGE_NAME_FOR_PROMPT)
        
        # Set output language dropdown
        if config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT in ["English", "Portuguese"]:
            self.output_language_var.set(config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT)

    def _get_pygame_output_devices(self) -> tuple[str, ...]:
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
        # Input devices (PyAudio)
        pa = pyaudio.PyAudio()
        input_devices = ["Default"]
        self.input_device_map = {"Default": None}
        try:
            default_info = pa.get_default_input_device_info()
            self.input_device_map["Default"] = default_info['index']
            # input_devices.append(f"Default ({default_info['name']})") # Already handled by default value

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
                # output_devices.append(f"Default ({pygame_devices[0]})") # Default is just None for Pygame devicename
                for device_name in pygame_devices:
                    output_devices.append(device_name)
                    self.output_device_map[device_name] = device_name # Store the name itself
        except Exception as e:
            print(f"Error populating output devices: {e}")
        self.output_device_combo.configure(values=output_devices)
        self.output_device_var.set(output_devices[0] if output_devices else "No devices found")


    def on_input_device_change(self, choice):
        config.PYAUDIO_INPUT_DEVICE_INDEX = self.input_device_map.get(choice)
        print(f"GUI: Selected Input Device: {choice} -> Index {config.PYAUDIO_INPUT_DEVICE_INDEX}")

    def on_output_device_change(self, choice):
        config.PYAUDIO_OUTPUT_DEVICE_NAME = self.output_device_map.get(choice)
        print(f"GUI: Selected Output Device: {choice} -> Name {config.PYAUDIO_OUTPUT_DEVICE_NAME}")
        # Re-initialize pygame mixer if it was already initialized, to use new device
        if app_globals.pygame_mixer_initialized.is_set():
            pygame.mixer.quit()
            app_globals.pygame_mixer_initialized.clear()
            # The core logic will re-initialize it when needed
            print("GUI: Pygame mixer will re-initialize with new device on next playback.")


    def update_speaking_status(self, is_speaking: bool):
        status = "Status: Speaking..." if is_speaking else "Status: Idle"
        self.speaking_status_var.set(status)
        self.speaking_status_label.configure(text_color="green" if is_speaking else "gray")

    def update_transcription(self, text: str):
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
        
        # Devices (already set by on_..._change methods, but ensure they are current)
        config.PYAUDIO_INPUT_DEVICE_INDEX = self.input_device_map.get(self.input_device_var.get())
        config.PYAUDIO_OUTPUT_DEVICE_NAME = self.output_device_map.get(self.output_device_var.get())
        print(f"GUI: Config Applied - Input Device Index: {config.PYAUDIO_INPUT_DEVICE_INDEX}, Output Device Name: {config.PYAUDIO_OUTPUT_DEVICE_NAME}")


    def start_translation_session(self):
        print("GUI: Start button clicked")
        self.apply_config_from_gui()

        if not config.AZ_OPENAI_ENDPOINT or not config.AZ_OPENAI_KEY:
            self.update_speaking_status(False) # Show error in status or a dialog
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
        print("GUI Core Logic Thread: Started")
        # Initialize Pygame mixer with selected device (or default)
        # This needs to happen in the thread that will use it, or ensure it's thread-safe
        # For now, initialize_pygame_mixer_if_needed handles its own thread safety with the Event.
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
                on_close=on_ws_close_new # This will set app_globals.done on close
            )
            self.ws_thread = threading.Thread(target=app_globals.ws_instance_global.run_forever, daemon=True)
            self.ws_thread.start()

        # --- Core Loop (monitor done flag) ---
        try:
            while not app_globals.done.is_set():
                # Check for stop command from translated history (optional for GUI version)
                # stop_command = "parar gravação." # Example
                # with app_globals.translated_speech_history_lock:
                #    if app_globals.translated_speech_history and stop_command in app_globals.translated_speech_history[-1].lower():
                #        print(f"🏁 COMMAND: '{stop_command}' detected. Stopping...")
                #        app_globals.done.set()
                #        break
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
        # translator_llm_agent_worker will signal tts_worker
        # tts_worker will signal playback_worker

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
        
        # Log final histories (optional for GUI, could be a save to file feature)
        # print("\n📜 Final Native Speech History (Processed by LLM):")
        # print("\n".join(app_globals.native_speech_history_processed_by_llm))
        # print("\n🗣️ Final Translated Speech History:")
        # print("\n".join(app_globals.translated_speech_history))


    def stop_translation_session(self):
        print("GUI: Stop button clicked")
        app_globals.done.set() # Signal all threads and loops to stop
        # self.core_logic_thread will see this and start its cleanup.
        # GUI elements will be re-enabled by _run_core_logic's finally block via reset_gui_after_stop

    def reset_gui_after_stop(self):
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.input_lang_combo.configure(state="normal")
        self.output_lang_combo.configure(state="normal")
        self.input_device_combo.configure(state="normal")
        self.output_device_combo.configure(state="normal")
        self.update_speaking_status(False)
        self.speaking_status_var.set("Status: Stopped")
        print("GUI: Interface reset after stop.")


    def on_closing(self):
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
    app = App()
    app.mainloop()
