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
    
    # Import GUI and other necessary modules
    from gui.app_gui import App
    import config as config
    import globals as app_globals
else:
    # Use relative imports when imported as part of a package
    from .gui.app_gui import App
    import config as config
    import globals as app_globals

def main_new_dub():
    """Main function for the new_dub application - launches the GUI"""
    print("🚀 Starting New Dub Application with GUI...")

    if not config.AZ_OPENAI_ENDPOINT or not config.AZ_OPENAI_KEY:
        print("❌ CRITICAL: Azure OpenAI endpoint or key not configured in env.py. GUI might show an error.")

    if not config.ELEVENLABS_API_KEY:
        print("❌ CRITICAL: ElevenLabs API key not configured in env.py. GUI might show an error.")

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
