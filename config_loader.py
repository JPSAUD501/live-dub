import os
import json
from typing import Dict, Any

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'env.json')

# Default API configurations - only includes the essential keys
DEFAULT_API_CONFIG = {
    "AZ_OPENAI_ENDPOINT": "",
    "AZ_OPENAI_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "ELEVENLABS_VOICE_ID": ""
}

def load_api_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load API configuration from JSON file, or create with defaults if not exists"""
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                # Ensure all required keys exist by merging with defaults
                for key, value in DEFAULT_API_CONFIG.items():
                    if key not in config_data:
                        config_data[key] = value
                return config_data
        else:
            # Create default config file with empty values
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_API_CONFIG, f, indent=2)
            print(f"Created default API config file at {config_path}")
            return DEFAULT_API_CONFIG.copy()
    except Exception as e:
        print(f"Error loading API config: {e}")
        return DEFAULT_API_CONFIG.copy()

def save_api_config(config_data: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> bool:
    """Save API configuration to JSON file"""
    try:
        # Filter to only include the allowed keys
        filtered_config = {k: v for k, v in config_data.items() if k in DEFAULT_API_CONFIG}
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(filtered_config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving API config: {e}")
        return False

def update_config_module(api_config: Dict[str, Any]) -> None:
    """Update the config module with the loaded API configurations"""
    import config
    
    # Update API config values
    for key, value in api_config.items():
        if hasattr(config, key):
            setattr(config, key, value)
