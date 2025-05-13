import os
import json
from typing import Dict, Any

# File paths
ENV_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'env.json')
APP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_config.json')

# Default API configurations (sensitive data)
DEFAULT_ENV_CONFIG = {
    "AZ_OPENAI_ENDPOINT": "",
    "AZ_OPENAI_KEY": "",
    "ELEVENLABS_API_KEY": ""
}

# Default user-configurable settings
DEFAULT_APP_CONFIG = {
    "INPUT_LANGUAGE_NAME_FOR_PROMPT": "English",
    "OUTPUT_LANGUAGE_NAME_FOR_PROMPT": "Portuguese",
    "SCRIBE_LANGUAGE_CODE": "en",
    "TTS_OUTPUT_ENABLED": True,
    "ELEVENLABS_VOICE_ID": "CwhRBWXzGAHq8TQ4Fs17",  # Default voice ID (Marcos)
    "PYAUDIO_INPUT_DEVICE_INDEX": None,
    "PYAUDIO_OUTPUT_DEVICE_NAME": None
}

def load_api_config(config_path: str = ENV_CONFIG_PATH) -> Dict[str, Any]:
    """Load API configuration (sensitive data) from env.json file"""
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                # Ensure all required keys exist by merging with defaults
                for key, value in DEFAULT_ENV_CONFIG.items():
                    if key not in config_data:
                        config_data[key] = value
                return config_data
        else:
            # Create default config file with empty values
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_ENV_CONFIG, f, indent=2)
            print(f"Created default API config file at {config_path}")
            return DEFAULT_ENV_CONFIG.copy()
    except Exception as e:
        print(f"Error loading API config: {e}")
        return DEFAULT_ENV_CONFIG.copy()

def load_app_config(config_path: str = APP_CONFIG_PATH) -> Dict[str, Any]:
    """Load user-configurable app settings from app_config.json file"""
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                # Ensure all required keys exist by merging with defaults
                for key, value in DEFAULT_APP_CONFIG.items():
                    if key not in config_data:
                        config_data[key] = value
                return config_data
        else:
            # Create default config file
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_APP_CONFIG, f, indent=2)
            print(f"Created default app config file at {config_path}")
            return DEFAULT_APP_CONFIG.copy()
    except Exception as e:
        print(f"Error loading app config: {e}")
        return DEFAULT_APP_CONFIG.copy()

def save_api_config(config_data: Dict[str, Any], config_path: str = ENV_CONFIG_PATH) -> bool:
    """Save API configuration to env.json file"""
    try:
        # Filter to only include the allowed keys
        filtered_config = {k: v for k, v in config_data.items() if k in DEFAULT_ENV_CONFIG}
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(filtered_config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving API config: {e}")
        return False

def save_app_config(config_data: Dict[str, Any], config_path: str = APP_CONFIG_PATH) -> bool:
    """Save user-configurable app settings to app_config.json file"""
    try:
        # Filter to only include the allowed keys
        filtered_config = {k: v for k, v in config_data.items() if k in DEFAULT_APP_CONFIG}
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(filtered_config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving app config: {e}")
        return False

def update_config_module(api_config: Dict[str, Any], app_config: Dict[str, Any] = None) -> None:
    """Update the config module with the loaded configurations"""
    import config
    
    # Update API config values (env.json)
    for key, value in api_config.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    # Update app config values (app_config.json)
    if app_config:
        for key, value in app_config.items():
            if hasattr(config, key):
                setattr(config, key, value)
