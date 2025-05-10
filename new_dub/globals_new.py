import threading
import queue
import websocket  # For WebSocketApp type hint
from collections import deque
import pygame  # For pygame types and mixer

from . import config_new as config  # Add this import

# --- Application Control ---
done = threading.Event()  # Controls main loop and signals threads to stop

# --- Audio Buffering and Capture Control ---
audio_buffer_lock = threading.Lock()
full_audio_data = bytearray()  # Stores all raw audio data from PyAudio
audio_capture_active = threading.Event()
audio_capture_active.set()  # Controls PyAudio callback data collection

# --- WebSocket and VAD State ---
ws_app: websocket.WebSocketApp | None = None  # WebSocketApp instance, set in on_ws_open
ws_instance_global: websocket.WebSocketApp | None = None  # WebSocketApp instance, set in main.py
speech_active = threading.Event()  # Set by VAD when speech_started, cleared when speech_stopped
final_transcription_pending_for_current_utterance = threading.Event()  # Add this line

# --- Scribe Transcription Timing and State ---
utterance_start_time_monotonic: float | None = None
utterance_audio_start_byte_offset: int = 0
last_periodic_scribe_submission_time: float = 0.0
last_periodic_scribe_chunk_end_byte_offset: int = 0

# --- Queues ---
# Queue for Scribe transcriptions to be processed by the translator LLM agent
# Item format: (transcription_text: str)
scribe_to_translator_llm_queue = queue.Queue()

# Queue for translated text from LLM to be processed by TTS
# Item format: (segment_id: int, text_to_speak: str)
llm_to_tts_queue = queue.Queue()

# Queue for generated audio bytes from TTS to be played back
# Item format: (segment_id: int, audio_bytes: bytes | None)
tts_to_playback_queue = queue.Queue()

# --- LLM Translator Agent State ---
# Stores the most recent Scribe transcription fragments as individual items
# The maximum number is defined by config.LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE
recent_scribe_transcriptions = deque(maxlen=5)  # Default maxlen, will be updated from config
recent_scribe_transcriptions_lock = threading.Lock()

# Stores the history of what the translator LLM has decided to speak (in the target language)
# Changed from string to list of strings
translated_speech_history = []
translated_speech_history_lock = threading.Lock()

# Stores the history of the original language text that the LLM processed to produce translations
# Changed from string to list of strings
native_speech_history_processed_by_llm = []
native_speech_history_processed_by_llm_lock = threading.Lock()

# --- Segment ID Generation ---
next_segment_id = 0
segment_id_lock = threading.Lock()

def get_new_segment_id() -> int:
    global next_segment_id
    with segment_id_lock:
        current_id = next_segment_id
        next_segment_id += 1
        return current_id

# --- Pygame Mixer Initialization ---
pygame_mixer_initialized = threading.Event()

def initialize_pygame_mixer_if_needed():
    if not pygame_mixer_initialized.is_set():
        try:
            frequency = config.PYAUDIO_RATE  # e.g., 16000 Hz for pcm_16000
            size = -16  # Signed 16-bit PCM
            channels = 1  # TTS output is typically mono, Pygame mixer can upmix if device is stereo
            buffer_size = 2048  # Default is 4096, can be reduced for lower latency if needed

            if config.PYAUDIO_OUTPUT_DEVICE_NAME:
                print(f"🎧 Attempting to initialize Pygame mixer on device: {config.PYAUDIO_OUTPUT_DEVICE_NAME} (Freq: {frequency}, Size: {size}, Channels: {channels}, Buffer: {buffer_size})")
                pygame.mixer.init(
                    frequency=frequency,
                    size=size,
                    channels=channels,
                    buffer=buffer_size,
                    devicename=config.PYAUDIO_OUTPUT_DEVICE_NAME
                )
            else:
                print(f"🎧 Attempting to initialize Pygame mixer with default device (Freq: {frequency}, Size: {size}, Channels: {channels}, Buffer: {buffer_size}).")
                pygame.mixer.init(
                    frequency=frequency,
                    size=size,
                    channels=channels,
                    buffer=buffer_size
                )
            
            actual_freq, actual_format, actual_channels = pygame.mixer.get_init()
            print(f"✅ Pygame Mixer Initialized. Actual settings - Frequency: {actual_freq}, Format: {actual_format}, Channels: {actual_channels}")

            if actual_freq != frequency:
                print(f"⚠️ PYGAME_MIXER_WARNING: Requested frequency {frequency}Hz, but initialized at {actual_freq}Hz.")
            # Pygame format: positive for unsigned, negative for signed. actual_format is bit size.
            # We request -16 (signed 16-bit). Pygame returns 16 (unsigned) or -16 (signed) for format.
            # So, if actual_format is 16 and size is -16, it's okay if it means 16-bit.
            # If actual_format is abs(size) and actual_format has different sign convention, it's okay.
            # The key is that the bit depth matches.
            if abs(actual_format) != abs(size): 
                print(f"⚠️ PYGAME_MIXER_WARNING: Requested format (bit depth) {abs(size)}, but initialized at {abs(actual_format)}.")
            
            # It's common for the mixer to initialize in stereo even if mono is requested,
            # especially if the default device is stereo. The play_audio_pygame function
            # should handle mono-to-stereo conversion if needed.
            if actual_channels != channels and actual_channels == 2 and channels == 1:
                 print(f"ℹ️ PYGAME_MIXER_INFO: Requested {channels} channel (mono), but initialized at {actual_channels} channels (stereo). Playback will adapt.")
            elif actual_channels != channels:
                 print(f"⚠️ PYGAME_MIXER_WARNING: Requested channels {channels}, but initialized at {actual_channels}.")

            pygame_mixer_initialized.set()
        except pygame.error as e:
            print(f"❌ PYGAME_MIXER_ERROR: Failed to initialize Pygame mixer: {e}")
            # Decide if this is critical enough to stop the app or just disable playback
            # For now, we'll let it continue but TTS/playback might fail.

# --- For logging/debugging ---
all_scribe_transcriptions_log = []  # Optional: to store all raw Scribe outputs for debugging
