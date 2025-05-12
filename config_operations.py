import pyaudio
import pygame
from openai import AzureOpenAI
from elevenlabs.client import ElevenLabs
import config

def initialize_pyaudio_settings():
    """Initialize PyAudio settings and get sample width"""
    p_audio_temp_instance = None
    try:
        p_audio_temp_instance = pyaudio.PyAudio()
        sample_width = p_audio_temp_instance.get_sample_size(config.PYAUDIO_FORMAT)
        return sample_width
    except Exception as e:
        print(f"⚠️ CONFIG WARNING: Could not determine PYAUDIO_SAMPLE_WIDTH using PyAudio: {e}. Defaulting to 2.")
        return 2
    finally:
        if p_audio_temp_instance:
            p_audio_temp_instance.terminate()

def compute_ws_url():
    """Compute WebSocket URL based on the OpenAI endpoint"""
    az_endpoint_normalized = config.AZ_OPENAI_ENDPOINT.rstrip('/') if config.AZ_OPENAI_ENDPOINT else ""
    if az_endpoint_normalized:
        return (az_endpoint_normalized.replace("https://", "wss://").replace("http://", "ws://") +
                f"/openai/realtime?api-version={config.AZ_API_VERSION_REALTIME}&intent=transcription")
    else:
        print("⚠️ CONFIG WARNING: AZ_OPENAI_ENDPOINT not set. WebSocket URL cannot be constructed.")
        return ""

def initialize_azure_openai_client():
    """Initialize the Azure OpenAI client"""
    if config.AZ_OPENAI_ENDPOINT and config.AZ_OPENAI_KEY:
        try:
            client_az_llm = AzureOpenAI(
                api_version=config.AZ_OPENAI_API_VERSION,
                azure_endpoint=config.AZ_OPENAI_ENDPOINT,
                api_key=config.AZ_OPENAI_KEY
            )
            print(f"✅ Azure OpenAI client for LLM ({config.AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME}) initialized.")
            return client_az_llm
        except Exception as e:
            print(f"❌ CONFIG ERROR: Failed to initialize AzureOpenAI client for LLM: {e}")
    else:
        print("⚠️ CONFIG WARNING: Azure OpenAI Endpoint or Key not set. LLM client not initialized.")
    return None

def initialize_elevenlabs_client():
    """Initialize the ElevenLabs client"""
    if config.ELEVENLABS_API_KEY:
        try:
            elevenlabs_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
            print("✅ ElevenLabs client initialized.")
            return elevenlabs_client
        except Exception as e:
            print(f"❌ CONFIG ERROR: Failed to initialize ElevenLabs client: {e}")
    else:
        print("⚠️ CONFIG WARNING: ElevenLabs API key not set. Scribe services will not be available.")
    return None

def print_config_info():
    """Print configuration information"""
    print(f"CONFIG: Periodic Scribe Interval: {config.PERIODIC_SCRIBE_INTERVAL_S}s")
    print(f"CONFIG: Periodic Scribe Inter-Chunk Overlap: {config.PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS}ms")
    print(f"CONFIG: Final Scribe Pre-roll: {config.FINAL_SCRIBE_PRE_ROLL_MS}ms")
    print(f"CONFIG: Translator LLM Model: {config.AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME}")
    print(f"CONFIG: Translator LLM Context Window: {config.LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE} items")
    print(f"CONFIG: Language Pair: {config.INPUT_LANGUAGE_NAME_FOR_PROMPT} → {config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT}")
    print(f"CONFIG: WebSocket URL: {config.WS_URL}")

def apply_config():
    """Apply configuration and initialize clients"""
    config.PYAUDIO_SAMPLE_WIDTH = initialize_pyaudio_settings()
    config.WS_URL = compute_ws_url()
    config.client_az_llm = initialize_azure_openai_client()
    config.elevenlabs_client = initialize_elevenlabs_client()
    print_config_info()
