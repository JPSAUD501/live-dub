import os
from openai import AzureOpenAI
from elevenlabs.client import ElevenLabs
import pyaudio
from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file located in the project root
# find_dotenv() will search for .env in parent directories from this file's location.
load_dotenv(find_dotenv())

# --- Configuration Variables ---
# Azure OpenAI service
AZ_OPENAI_ENDPOINT = os.getenv("AZ_OPENAI_ENDPOINT")
AZ_OPENAI_KEY = os.getenv("AZ_OPENAI_KEY")
AZ_OPENAI_API_VERSION = "2024-05-01-preview" # Remains as is, less likely to change frequently

GPT_4O_TRANSCRIBE_DEPLOYMENT_NAME = "gpt-4o-transcribe" # Remains as is

# --- Transcription Provider Configuration ---
TRANSCRIPTION_PROVIDER = os.getenv("TRANSCRIPTION_PROVIDER", "ELEVENLABS")

# Azure OpenAI Configuração para tradução com gpt-4.1-mini
AZ_TRANSLATION_MODEL = "gpt-4.1-mini" # Remains as is

# OpenAI TTS Configuration
AZ_TTS_MODEL = "gpt-4o-mini-tts"
AZ_TTS_VOICE = "echo"
TTS_OUTPUT_ENABLED = os.getenv("TTS_OUTPUT_ENABLED", "True").lower() == "true"

# --- TTS Provider Configuration ---
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "ELEVENLABS")
AZ_TTS_OUTPUT_FORMAT = "pcm"

# --- ElevenLabs TTS Configuration ---
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL_ID = "eleven_flash_v2_5"
ELEVENLABS_OUTPUT_FORMAT = "pcm_16000"
ELEVENLABS_OPTIMIZE_STREAMING_LATENCY = int(os.getenv("ELEVENLABS_OPTIMIZE_STREAMING_LATENCY", "0"))


# --- Language Configuration ---
INPUT_LANGUAGE_NAME_FOR_PROMPT = "Portuguese"
OUTPUT_LANGUAGE_NAME_FOR_PROMPT = "English"
GPT_4O_TRANSCRIBE_LANG_CODE = "pt"
WS_TRANSCRIPTION_LANG_CODE = "pt"

MAX_TRANSLATION_HISTORY_CHARS = int(os.getenv("MAX_TRANSLATION_HISTORY_CHARS", "5000"))
PRE_ROLL_MS = int(os.getenv("PRE_ROLL_MS", "1000"))
PERIODIC_TRANSCRIPTION_INTERVAL_S = float(os.getenv("PERIODIC_TRANSCRIPTION_INTERVAL_S", "2.0"))
PERIODIC_TRANSCRIPTION_OVERLAP_MS = int(os.getenv("PERIODIC_TRANSCRIPTION_OVERLAP_MS", "3000"))

# PyAudio Configuration
PYAUDIO_RATE = 16000
PYAUDIO_CHANNELS = 1
PYAUDIO_FORMAT = pyaudio.paInt16
PYAUDIO_FRAMES_PER_BUFFER = 512

# --- Playback speed control ---
PLAYBACK_SPEED = float(os.getenv("PLAYBACK_SPEED", "1.0"))

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
