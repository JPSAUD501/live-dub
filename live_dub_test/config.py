import os
from openai import AzureOpenAI
from elevenlabs.client import ElevenLabs
import pyaudio

# Attempt to import configurations from env.py located in the project root.
# This assumes that the script is run from the project root (d:\GitHub\live-dub)
# or that the project root is in PYTHONPATH.
try:
    import env
except ImportError:
    print("CRITICAL ERROR: env.py not found in project root or not importable. "
          "Please create env.py with your configurations (e.g., API keys). "
          "The application cannot continue without it.")
    raise SystemExit("env.py not found or not importable. Ensure it is in the project root (d:\\GitHub\\live-dub).")


# --- Configuration Variables ---
# Azure OpenAI service
AZ_OPENAI_ENDPOINT = env.AZ_OPENAI_ENDPOINT
AZ_OPENAI_KEY = env.AZ_OPENAI_KEY
AZ_OPENAI_API_VERSION = "2024-05-01-preview" # Remains as is, less likely to change frequently

GPT_4O_TRANSCRIBE_DEPLOYMENT_NAME = "gpt-4o-transcribe" # Remains as is

# --- Transcription Provider Configuration ---
TRANSCRIPTION_PROVIDER = env.TRANSCRIPTION_PROVIDER

# Azure OpenAI Configuração para tradução com gpt-4.1-mini
AZ_TRANSLATION_MODEL = "gpt-4.1-mini" # Remains as is

# OpenAI TTS Configuration
AZ_TTS_MODEL = "gpt-4o-mini-tts"
AZ_TTS_VOICE = "echo"
TTS_OUTPUT_ENABLED = env.TTS_OUTPUT_ENABLED

# --- TTS Provider Configuration ---
TTS_PROVIDER = env.TTS_PROVIDER
AZ_TTS_OUTPUT_FORMAT = "pcm"

# --- ElevenLabs TTS Configuration ---
ELEVENLABS_API_KEY = env.ELEVENLABS_API_KEY
ELEVENLABS_VOICE_ID = env.ELEVENLABS_VOICE_ID
ELEVENLABS_MODEL_ID = "eleven_flash_v2_5"
ELEVENLABS_OUTPUT_FORMAT = "pcm_16000"
ELEVENLABS_OPTIMIZE_STREAMING_LATENCY = env.ELEVENLABS_OPTIMIZE_STREAMING_LATENCY


# --- Language Configuration ---
INPUT_LANGUAGE_NAME_FOR_PROMPT = "Portuguese"
OUTPUT_LANGUAGE_NAME_FOR_PROMPT = "English"
GPT_4O_TRANSCRIBE_LANG_CODE = "pt"
WS_TRANSCRIPTION_LANG_CODE = "pt"

MAX_TRANSLATION_HISTORY_CHARS = env.MAX_TRANSLATION_HISTORY_CHARS
PRE_ROLL_MS = env.PRE_ROLL_MS
PERIODIC_TRANSCRIPTION_INTERVAL_S = env.PERIODIC_TRANSCRIPTION_INTERVAL_S
PERIODIC_TRANSCRIPTION_OVERLAP_MS = env.PERIODIC_TRANSCRIPTION_OVERLAP_MS

# PyAudio Configuration
PYAUDIO_RATE = 16000
PYAUDIO_CHANNELS = 1
PYAUDIO_FORMAT = pyaudio.paInt16
PYAUDIO_FRAMES_PER_BUFFER = 512

# --- Playback speed control ---
PLAYBACK_SPEED = env.PLAYBACK_SPEED

# --- Selected audio device indices ---
PYAUDIO_INPUT_DEVICE_INDEX = None   # set by device_selector
PYAUDIO_OUTPUT_DEVICE_INDEX = None  # set by device_selector
PYAUDIO_OUTPUT_DEVICE_NAME = None   # set by device_selector

# --- Determine PYAUDIO_SAMPLE_WIDTH safely ---
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

# WebSocket Configuration
WS_API_VERSION_REALTIME = "2025-04-01-preview"
az_endpoint_normalized = AZ_OPENAI_ENDPOINT.rstrip('/') if AZ_OPENAI_ENDPOINT else ""
WS_URL = ""
if az_endpoint_normalized:
    WS_URL = (az_endpoint_normalized.replace("https://", "wss://").replace("http://", "ws://") +
              f"/openai/realtime?api-version={WS_API_VERSION_REALTIME}&intent=transcription")
else:
    print("⚠️ CONFIG WARNING: AZ_OPENAI_ENDPOINT not set. WebSocket URL cannot be constructed.")


# ─── Azure OpenAI client for Transcription & Translation ────────────────
client_az_transcription = None
client_az_translation = None

if AZ_OPENAI_ENDPOINT and AZ_OPENAI_KEY:
    try:
        common_azure_client = AzureOpenAI(
            api_version=AZ_OPENAI_API_VERSION,
            azure_endpoint=AZ_OPENAI_ENDPOINT,
            api_key=AZ_OPENAI_KEY # Changed from azure_ad_token to api_key for typical key usage
        )
        client_az_transcription = common_azure_client
        client_az_translation = common_azure_client
        print("✅ Azure OpenAI clients initialized.")
    except Exception as e:
        print(f"❌ CONFIG ERROR: Failed to initialize AzureOpenAI clients: {e}")
else:
    print("⚠️ CONFIG WARNING: Azure OpenAI Endpoint or Key not set. Azure clients not initialized.")


# --- ElevenLabs Client Initialization ---
elevenlabs_client = None
if ELEVENLABS_API_KEY and ELEVENLABS_API_KEY != "your_elevenlabs_api_key": # Check for actual key
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("✅ ElevenLabs client initialized.")
    except Exception as e:
        print(f"❌ CONFIG ERROR: Failed to initialize ElevenLabs client: {e}")
else:
    if not ELEVENLABS_API_KEY:
        print("⚠️ CONFIG WARNING: ElevenLabs API key not set. ElevenLabs services will not be available.")
    elif ELEVENLABS_API_KEY == "your_elevenlabs_api_key":
        print("⚠️ CONFIG WARNING: ElevenLabs API key is a placeholder. Please replace it with your actual key. ElevenLabs services may not be available.")

    if TTS_PROVIDER == "ELEVENLABS" or TRANSCRIPTION_PROVIDER == "ELEVENLABS":
        # This warning will be shown if the key is missing or placeholder and ElevenLabs is selected as a provider
        pass # The more specific warnings above cover this.
