import pyaudio

# --- API Versions and Constants ---
AZ_OPENAI_API_VERSION = "2024-05-01-preview"
AZ_API_VERSION_REALTIME = "2025-04-01-preview"
ELEVENLABS_SCRIBE_MODEL_ID = "scribe_v1"
ELEVENLABS_MODEL_ID = "eleven_flash_v2_5"
ELEVENLABS_OUTPUT_FORMAT = "pcm_16000"

# --- API Configurations (will be loaded from env.json) ---
AZ_OPENAI_ENDPOINT = ""
AZ_OPENAI_KEY = ""
ELEVENLABS_API_KEY = ""

# --- Additional API Configuration with defaults ---
AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME = "gpt-4.1-mini"
ELEVENLABS_OPTIMIZE_STREAMING_LATENCY = 1
# Default voice ID (Marcos)
DEFAULT_VOICE_ID = "CwhRBWXzGAHq8TQ4Fs17"
ELEVENLABS_VOICE_ID = DEFAULT_VOICE_ID  # Will be updated from app_config.json

# --- Application Configurations (fixed, not editable through GUI) ---
INPUT_LANGUAGE_NAME_FOR_PROMPT = "English"
OUTPUT_LANGUAGE_NAME_FOR_PROMPT = "Portuguese"
SCRIBE_LANGUAGE_CODE = "en"
TTS_OUTPUT_ENABLED = True
PERIODIC_SCRIBE_INTERVAL_S = 5.0
PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS = 500
FINAL_SCRIBE_PRE_ROLL_MS = 500
LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE = 5
MAX_NATIVE_HISTORY_CHARS = 5000
MAX_TRANSLATED_HISTORY_CHARS = 5000
AZ_VAD_SILENCE_TIMEOUT_MS = 500
AZ_VAD_PRE_ROLL_MS = 300

# --- PyAudio Configuration ---
PYAUDIO_RATE = 16000
PYAUDIO_CHANNELS = 1
PYAUDIO_FORMAT = pyaudio.paInt16
PYAUDIO_FRAMES_PER_BUFFER = 1024
PYAUDIO_INPUT_DEVICE_INDEX = None
PYAUDIO_OUTPUT_DEVICE_NAME = None
PYAUDIO_SAMPLE_WIDTH = 2  # Will be updated by config_operations

# --- WebSocket Configuration ---
WS_URL = ""  # Will be computed by config_operations

# --- Clients (initialized by config_operations) ---
client_az_llm = None
elevenlabs_client = None
