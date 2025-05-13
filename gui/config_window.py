"""Configuration window for the Live Dubbing Application."""

import customtkinter
import tkinter as tk
import os
import sys

# Ensure parent directory is in sys.path for module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import config
import config_loader
import config_operations

class ConfigWindow(customtkinter.CTkToplevel):
    """Configuration window for the Live Dubbing Application."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("API Credentials")
        self.geometry("600x400")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.api_config = config_loader.load_api_config()
        
        # Create API credentials panel
        self.create_api_credentials_panel()
        
        # Create buttons at bottom
        self.button_frame = customtkinter.CTkFrame(self)
        self.button_frame.pack(fill="x", padx=10, pady=10)
        
        self.save_button = customtkinter.CTkButton(
            self.button_frame, text="Save Changes", command=self.save_config
        )
        self.save_button.pack(side="right", padx=5)
        
        self.cancel_button = customtkinter.CTkButton(
            self.button_frame, text="Cancel", command=self.on_closing
        )
        self.cancel_button.pack(side="right", padx=5)

    def create_api_credentials_panel(self):
        """Create the API credentials configuration panel."""
        main_frame = customtkinter.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        title_label = customtkinter.CTkLabel(
            main_frame, 
            text="API Credentials", 
            font=customtkinter.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(5, 15))
        
        # Create a grid for the entries
        entries_frame = customtkinter.CTkFrame(main_frame)
        entries_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Azure OpenAI
        customtkinter.CTkLabel(entries_frame, text="Azure OpenAI Endpoint:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.az_endpoint_entry = customtkinter.CTkEntry(entries_frame, width=400)
        self.az_endpoint_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        self.az_endpoint_entry.insert(0, self.api_config.get("AZ_OPENAI_ENDPOINT", ""))
        
        customtkinter.CTkLabel(entries_frame, text="Azure OpenAI Key:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.az_key_entry = customtkinter.CTkEntry(entries_frame, width=400, show="*")
        self.az_key_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.az_key_entry.insert(0, self.api_config.get("AZ_OPENAI_KEY", ""))
        
        # ElevenLabs
        customtkinter.CTkLabel(entries_frame, text="ElevenLabs API Key:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.el_key_entry = customtkinter.CTkEntry(entries_frame, width=400, show="*")
        self.el_key_entry.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        self.el_key_entry.insert(0, self.api_config.get("ELEVENLABS_API_KEY", ""))
        
        customtkinter.CTkLabel(entries_frame, text="ElevenLabs Voice ID:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.el_voice_entry = customtkinter.CTkEntry(entries_frame, width=400)
        self.el_voice_entry.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        self.el_voice_entry.insert(0, self.api_config.get("ELEVENLABS_VOICE_ID", ""))
        
        # Toggle show/hide password
        self.show_passwords_var = tk.BooleanVar(value=False)
        self.show_passwords_cb = customtkinter.CTkCheckBox(
            entries_frame, text="Show passwords", variable=self.show_passwords_var, 
            command=self.toggle_password_visibility
        )
        self.show_passwords_cb.grid(row=4, column=1, sticky="w", padx=10, pady=10)
    
    def toggle_password_visibility(self):
        """Toggle visibility of password fields."""
        show_char = "" if self.show_passwords_var.get() else "*"
        self.az_key_entry.configure(show=show_char)
        self.el_key_entry.configure(show=show_char)
    
    def save_config(self):
        """Save API configuration to file."""
        # Update API config from form fields
        self.api_config["AZ_OPENAI_ENDPOINT"] = self.az_endpoint_entry.get().strip()
        self.api_config["AZ_OPENAI_KEY"] = self.az_key_entry.get().strip()
        self.api_config["ELEVENLABS_API_KEY"] = self.el_key_entry.get().strip()
        self.api_config["ELEVENLABS_VOICE_ID"] = self.el_voice_entry.get().strip()
        
        # Save to file
        config_loader.save_api_config(self.api_config)

        # Update the running configuration
        config_loader.update_config_module(self.api_config)
        
        # Re-apply config operations
        config.WS_URL = config_operations.compute_ws_url()
        config.client_az_llm = config_operations.initialize_azure_openai_client()
        config.elevenlabs_client = config_operations.initialize_elevenlabs_client()
        
        self.show_message("Success", "API credentials saved successfully!")
        self.destroy()
    
    def show_message(self, title, message):
        """Show a modal message dialog."""
        messagebox = customtkinter.CTkToplevel(self)
        messagebox.title(title)
        messagebox.geometry("400x200")
        messagebox.grab_set()  # Make modal
        
        # Center on parent
        window_width = 400
        window_height = 200
        position_x = self.winfo_x() + (self.winfo_width() // 2) - (window_width // 2)
        position_y = self.winfo_y() + (self.winfo_height() // 2) - (window_height // 2)
        messagebox.geometry(f"{window_width}x{window_height}+{position_x}+{position_y}")
        
        # Add content
        msg_frame = customtkinter.CTkFrame(messagebox, corner_radius=0)
        msg_frame.pack(fill="both", expand=True)
        
        msg_label = customtkinter.CTkLabel(
            msg_frame, text=message, wraplength=380, justify="left")
        msg_label.pack(padx=20, pady=20, expand=True)
        
        ok_button = customtkinter.CTkButton(
            msg_frame, text="OK", command=messagebox.destroy, width=100)
        ok_button.pack(pady=10)
        
        # Make sure we destroy the window if user clicks the X
        messagebox.protocol("WM_DELETE_WINDOW", messagebox.destroy)
    
    def on_closing(self):
        """Handle window close event."""
        self.destroy()
