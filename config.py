import pyaudio
from openai import AzureOpenAI
from elevenlabs.client import ElevenLabs

try:
    import env as project_env
except ImportError:
    print("CRITICAL ERROR: env.py not found or not importable. "
          "Please ensure env.py exists with your configurations. "
          "The application cannot continue without it.")
    raise SystemExit("env.py not found or not importable.")

# --- Azure OpenAI Service ---
AZ_OPENAI_ENDPOINT = getattr(project_env, 'AZ_OPENAI_ENDPOINT', None)
AZ_OPENAI_KEY = getattr(project_env, 'AZ_OPENAI_KEY', None)
AZ_OPENAI_API_VERSION = "2024-05-01-preview"
AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME = getattr(project_env, 'AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME', "gpt-4o-mini")

# --- ElevenLabs Configuration ---
ELEVENLABS_API_KEY = getattr(project_env, 'ELEVENLABS_API_KEY', None)
ELEVENLABS_VOICE_ID = getattr(project_env, 'ELEVENLABS_VOICE_ID', None)
ELEVENLABS_SCRIBE_MODEL_ID = "scribe_v1"
ELEVENLABS_MODEL_ID = "eleven_flash_v2_5" # Model for TTS
ELEVENLABS_OUTPUT_FORMAT = "pcm_16000" # Explicitly request PCM at 16kHz

# --- WebSocket Configuration (Azure Speech Service for VAD) ---
WS_API_VERSION_REALTIME = "2025-04-01-preview"
az_endpoint_normalized = AZ_OPENAI_ENDPOINT.rstrip('/') if AZ_OPENAI_ENDPOINT else ""
WS_URL = ""
if az_endpoint_normalized:
    WS_URL = (az_endpoint_normalized.replace("https://", "wss://").replace("http://", "ws://") +
              f"/openai/realtime?api-version={WS_API_VERSION_REALTIME}&intent=transcription")
else:
    print("⚠️ CONFIG WARNING: AZ_OPENAI_ENDPOINT not set. WebSocket URL cannot be constructed.")

# --- Language Configuration (for prompts, etc.) ---
INPUT_LANGUAGE_NAME_FOR_PROMPT = getattr(project_env, 'INPUT_LANGUAGE_NAME_FOR_PROMPT', "English")
OUTPUT_LANGUAGE_NAME_FOR_PROMPT = getattr(project_env, 'OUTPUT_LANGUAGE_NAME_FOR_PROMPT', "Portuguese")
SCRIBE_LANGUAGE_CODE = getattr(project_env, 'SCRIBE_LANGUAGE_CODE', "en")

# --- TTS Configuration ---
TTS_OUTPUT_ENABLED = getattr(project_env, 'TTS_OUTPUT_ENABLED', True)

# --- Scribe Transcription Configuration ---
PERIODIC_SCRIBE_INTERVAL_S = float(getattr(project_env, 'PERIODIC_SCRIBE_INTERVAL_S', "3.0")) # Changed default to 3.0 to match example
PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS = int(getattr(project_env, 'PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS', "250")) # NEW
FINAL_SCRIBE_PRE_ROLL_MS = int(getattr(project_env, 'FINAL_SCRIBE_PRE_ROLL_MS', "500")) # Changed default to 500

# --- PyAudio Configuration ---
PYAUDIO_RATE = 16000
PYAUDIO_CHANNELS = 1
PYAUDIO_FORMAT = pyaudio.paInt16
PYAUDIO_FRAMES_PER_BUFFER = 1024
PYAUDIO_INPUT_DEVICE_INDEX = None  # Will be set by device selector
PYAUDIO_OUTPUT_DEVICE_NAME = None # Will be set by device selector for Pygame

_p_audio_temp_instance = None
try:
    _p_audio_temp_instance = pyaudio.PyAudio()
    PYAUDIO_SAMPLE_WIDTH = _p_audio_temp_instance.get_sample_size(PYAUDIO_FORMAT)
except Exception as e:
    print(f"⚠️ CONFIG WARNING: Could not determine PYAUDIO_SAMPLE_WIDTH using PyAudio: {e}. Defaulting to 2.")
    PYAUDIO_SAMPLE_WIDTH = 2
finally:
    if _p_audio_temp_instance:
        _p_audio_temp_instance.terminate()
        del _p_audio_temp_instance

# --- LLM Translator Agent Configuration ---
LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE = int(getattr(project_env, 'LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE', 5))
MAX_NATIVE_HISTORY_CHARS = int(getattr(project_env, 'MAX_NATIVE_HISTORY_CHARS', 5000))
MAX_TRANSLATED_HISTORY_CHARS = int(getattr(project_env, 'MAX_TRANSLATED_HISTORY_CHARS', 5000))

# --- VAD Configuration (for Azure WebSocket) ---
AZ_VAD_SILENCE_TIMEOUT_MS = 500  # Reduced from 2000ms
AZ_VAD_PRE_ROLL_MS = 300

# --- Azure OpenAI Client (for Translator LLM) ---
client_az_llm = None
if AZ_OPENAI_ENDPOINT and AZ_OPENAI_KEY:
    try:
        client_az_llm = AzureOpenAI(
            api_version=AZ_OPENAI_API_VERSION,
            azure_endpoint=AZ_OPENAI_ENDPOINT,
            api_key=AZ_OPENAI_KEY
        )
        print(f"✅ Azure OpenAI client for LLM ({AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME}) initialized.")
    except Exception as e:
        print(f"❌ CONFIG ERROR: Failed to initialize AzureOpenAI client for LLM: {e}")
else:
    print("⚠️ CONFIG WARNING: Azure OpenAI Endpoint or Key not set. LLM client not initialized.")

# --- ElevenLabs Client (for Scribe) ---
elevenlabs_client = None
if ELEVENLABS_API_KEY:
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("✅ ElevenLabs client initialized.")
    except Exception as e:
        print(f"❌ CONFIG ERROR: Failed to initialize ElevenLabs client: {e}")
else:
    print("⚠️ CONFIG WARNING: ElevenLabs API key not set. Scribe services will not be available.")

print(f"CONFIG_NEW: Periodic Scribe Interval: {PERIODIC_SCRIBE_INTERVAL_S}s")
print(f"CONFIG_NEW: Periodic Scribe Inter-Chunk Overlap: {PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS}ms") # UPDATED
print(f"CONFIG_NEW: Final Scribe Pre-roll: {FINAL_SCRIBE_PRE_ROLL_MS}ms")
print(f"CONFIG_NEW: Translator LLM Model: {AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME}")
print(f"CONFIG_NEW: Translator LLM Context Window: {LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE} items")
