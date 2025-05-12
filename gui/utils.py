"""Utility functions for the Live Dubbing Application GUI."""

import customtkinter
import tkinter as tk

def create_modal_dialog(parent, title, message, width=400, height=200):
    """Create a modal dialog with a message and OK button.
    
    Args:
        parent: The parent window
        title: The dialog title
        message: The message to display
        width: Width of the dialog window
        height: Height of the dialog window
        
    Returns:
        The dialog window object
    """
    dialog = customtkinter.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry(f"{width}x{height}")
    dialog.grab_set()  # Make modal
    
    # Center on parent
    position_x = parent.winfo_x() + (parent.winfo_width() // 2) - (width // 2)
    position_y = parent.winfo_y() + (parent.winfo_height() // 2) - (height // 2)
    dialog.geometry(f"{width}x{height}+{position_x}+{position_y}")
    
    # Add content
    msg_frame = customtkinter.CTkFrame(dialog, corner_radius=0)
    msg_frame.pack(fill="both", expand=True)
    
    msg_label = customtkinter.CTkLabel(
        msg_frame, text=message, wraplength=width-20, justify="left")
    msg_label.pack(padx=20, pady=20, expand=True)
    
    ok_button = customtkinter.CTkButton(
        msg_frame, text="OK", command=dialog.destroy, width=100)
    ok_button.pack(pady=10)
    
    # Make sure we destroy the window if user clicks the X
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    
    return dialog

def setup_gui_style():
    """Configure the global GUI style settings."""
    customtkinter.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
    customtkinter.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"
