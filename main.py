import threading
import time
import os
import sys
import pygame

# Fix imports to work both when run directly and as part of a package
if __name__ == "__main__":
    # Add the parent directory to sys.path to enable absolute imports
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Load and apply configuration first
    import config_loader
    # Load configurations from JSON files
    api_config = config_loader.load_api_config()
    app_config = config_loader.load_app_config()
    
    # Import other modules after loading configuration
    import config
    import config_operations
    
    # Update config module with loaded values
    config_loader.update_config_module(api_config, app_config)
    
    # Apply configuration and initialize clients
    config_operations.apply_config()
    
    # Setup GUI style
    from gui.utils import setup_gui_style
    setup_gui_style()
    
    # Import GUI and other necessary modules
    from gui import App
    import globals as app_globals
else:
    # Use relative imports when imported as part of a package
    from .gui import App
    import config as config
    import globals as app_globals

def main_new_dub():
    """Main function for the new_dub application - launches the GUI"""
    print("🚀 Starting Live Dubbing Application with GUI...")

    if not config.AZ_OPENAI_ENDPOINT or not config.AZ_OPENAI_KEY:
        print("❌ CRITICAL: Azure OpenAI endpoint or key not configured. GUI might show an error.")

    if not config.ELEVENLABS_API_KEY:
        print("❌ CRITICAL: ElevenLabs API key not configured. GUI might show an error.")

    # --- Launch GUI ---
    app = App()
    
    try:
        app.mainloop()
    except KeyboardInterrupt:
        print("\n⌨️ KEYBOARD INTERRUPT DETECTED IN MAIN.PY. GUI should handle shutdown.")
    finally:
        print("\n🧼 Main.py: Application GUI has closed. Performing final cleanup if any...")
        if pygame.get_init():
             pygame.quit()
        print("\n✅ Main.py: Application Exiting.")

if __name__ == "__main__":
    main_new_dub()
