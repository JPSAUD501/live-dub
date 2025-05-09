import threading
import queue
import pygame
import websocket # For WebSocketApp type hint
from . import config

# --- Global State ---
translation_history = ""
translated_output_history = ""
original_speech_history = "" # History of speech in the original language
all_results = [] # Stores final transcriptions from 4o
done = False # Controls main loop and signals threads to stop

next_segment_id = 0
segment_id_lock = threading.Lock()

def get_next_segment_id():
    global next_segment_id
    with segment_id_lock:
        current_id = next_segment_id
        next_segment_id += 1
        return current_id

# Global Audio Buffer & Timing State
audio_buffer_lock = threading.Lock()
full_audio_data = bytearray() # Stores all raw audio data from PyAudio
audio_capture_active = threading.Event()
audio_capture_active.set() # Controls PyAudio callback data collection

utterance_audio_start_byte_offset = 0 # Byte offset in full_audio_data where current utterance started
utterance_start_time_monotonic = None # Monotonic time when current utterance started (speech_started event)

# WebSocket and periodic transcription state
ws_app: websocket.WebSocketApp | None = None # WebSocketApp instance, set in on_ws_open
ws_instance_global: websocket.WebSocketApp | None = None # WebSocketApp instance, set in main.py
speech_active = threading.Event() # Set when speech_started, cleared when speech_stopped
last_periodic_transcription_time = 0.0 # Tracks time of last periodic transcription
current_sdk_interim_text = "" # Accumulates interim transcription text from WebSocket deltas
# NEW ────── byte offset (in full_audio_data) of last periodic chunk end
last_periodic_transcription_byte_offset = 0
first_audio_packet_sent_this_utterance = False  # For logging first audio packet sent via WebSocket

# --- Queues ---
transcription_to_translation_queue = queue.Queue() # (sdk_text, text_4o, is_final)
text_to_speech_queue = queue.Queue() # (text_to_speak)
audio_bytes_to_playback_queue = queue.Queue() # (audio_bytes)

# Initialize Pygame Mixer - default only
def initialize_pygame_mixer():
    """Initializes the pygame mixer, usando dispositivo selecionado se houver."""
    try:
        # Desired audio format for playback (matching PCM from TTS)
        frequency = config.PYAUDIO_RATE # e.g., 16000 Hz
        size = -16  # Signed 16-bit
        channels = config.PYAUDIO_CHANNELS # e.g., 1 for mono

        if config.PYAUDIO_OUTPUT_DEVICE_NAME:
            print(f"🎧 Attempting to initialize Pygame mixer on device: {config.PYAUDIO_OUTPUT_DEVICE_NAME} (Freq: {frequency}, Size: {size}, Channels: {channels})")
            pygame.mixer.init(frequency=frequency, size=size, channels=channels, devicename=config.PYAUDIO_OUTPUT_DEVICE_NAME)
        else:
            print(f"🎧 Attempting to initialize Pygame mixer with default device (Freq: {frequency}, Size: {size}, Channels: {channels}).")
            pygame.mixer.init(frequency=frequency, size=size, channels=channels)
        
        # Verify actual initialized settings
        actual_freq, actual_format, actual_channels = pygame.mixer.get_init()
        print(f"✅ Pygame Mixer Initialized. Actual settings - Frequency: {actual_freq}, Format: {actual_format}, Channels: {actual_channels}")

        if actual_freq != frequency:
            print(f"⚠️ PYGAME_MIXER_WARNING: Requested frequency {frequency}Hz, but initialized at {actual_freq}Hz. This might cause playback speed issues if audio data is {frequency}Hz.")
        if actual_format != size:
            print(f"⚠️ PYGAME_MIXER_WARNING: Requested format (bit size) {size}, but initialized at {actual_format}.")
        if actual_channels != channels:
            print(f"⚠️ PYGAME_MIXER_WARNING: Requested channels {channels}, but initialized at {actual_channels}.")

    except pygame.error as e:
        # If the device is not found, this error will now propagate.
        print(f"❌ CRITICAL PYGAME_MIXER_ERROR: Failed to init mixer: {e}")
        raise

