import threading
import queue
import websocket  # For WebSocketApp type hint
from collections import deque

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

# --- Scribe Transcription Timing and State ---
utterance_start_time_monotonic: float | None = None
utterance_audio_start_byte_offset: int = 0
last_periodic_scribe_submission_time: float = 0.0
last_periodic_scribe_chunk_end_byte_offset: int = 0

# --- Queues ---
# Queue for Scribe transcriptions to be processed by the translator LLM agent
# Item format: (transcription_text: str)
scribe_to_translator_llm_queue = queue.Queue()

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

# --- For logging/debugging ---
all_scribe_transcriptions_log = []  # Optional: to store all raw Scribe outputs for debugging
