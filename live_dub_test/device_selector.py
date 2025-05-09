import pyaudio
from . import config
import pygame
import pygame._sdl2.audio as sdl2_audio
from typing import Tuple

def get_pygame_output_devices(capture_devices: bool = False) -> Tuple[str, ...]:
    # Helper function based on the Stack Overflow article to get device names from Pygame
    init_by_me = not pygame.mixer.get_init()
    if init_by_me:
        pygame.mixer.init() # Temporarily init mixer if not already initialized
    
    devices = tuple(sdl2_audio.get_audio_device_names(capture_devices))
    
    if init_by_me:
        pygame.mixer.quit() # Quit if we initialized it here
    return devices

def select_audio_devices():
    p = pyaudio.PyAudio()

    # 1) Listar e selecionar apenas dispositivos de INPUT (using PyAudio)
    print("=== Input Devices (PyAudio) ===")
    input_devices_info = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info.get('maxInputChannels', 0) > 0:
            input_devices_info.append({'index': i, 'name': info['name'], 'channels': info['maxInputChannels']})
            print(f"{i}: {info['name']} (in:{info['maxInputChannels']})")
    
    selected_input_idx_str = input("Select Input Device [PyAudio index]: ")
    try:
        idx_in = int(selected_input_idx_str)
        # Validate selection against actual PyAudio indices
        if not any(dev['index'] == idx_in for dev in input_devices_info):
            print(f"Invalid input device index: {idx_in}. Please choose from the list.")
            # Optionally, raise an error or re-prompt
            raise ValueError("Invalid input device selection")
        config.PYAUDIO_INPUT_DEVICE_INDEX = idx_in
        selected_input_name = p.get_device_info_by_index(idx_in)['name']
        print(f"🎤 Input device selected: #{idx_in} - {selected_input_name}")
    except ValueError:
        print(f"Invalid input: '{selected_input_idx_str}'. Please enter a number.")
        # Handle error, e.g., exit or default
        raise # Or set a default / re-prompt

    # 2) Listar e selecionar apenas dispositivos de OUTPUT (using Pygame/SDL2)
    print("\n=== Output Devices (Pygame/SDL2) ===")
    # pygame.init() # Ensure pygame is initialized for sdl2_audio (mixer.init() in helper handles it)
    
    output_device_names_pygame = get_pygame_output_devices(False) # False for playback devices
    
    if not output_device_names_pygame:
        print("⚠️ No output devices found by Pygame/SDL2.")
        # Handle this case: maybe default, maybe error
        config.PYAUDIO_OUTPUT_DEVICE_NAME = None # Explicitly set to None
        # config.PYAUDIO_OUTPUT_DEVICE_INDEX can remain None or be set to -1
    else:
        for i, name in enumerate(output_device_names_pygame):
            print(f"{i}: {name}")
        
        selected_output_idx_str = input("Select Output Device [Pygame index]: ")
        try:
            idx_out_pygame = int(selected_output_idx_str)
            if 0 <= idx_out_pygame < len(output_device_names_pygame):
                config.PYAUDIO_OUTPUT_DEVICE_NAME = output_device_names_pygame[idx_out_pygame]
                # Store the Pygame list index. This index is specific to Pygame's list.
                config.PYAUDIO_OUTPUT_DEVICE_INDEX = idx_out_pygame 
                print(f"🎧 Output device selected: #{idx_out_pygame} - {config.PYAUDIO_OUTPUT_DEVICE_NAME}")
            else:
                print(f"Invalid output device index: {idx_out_pygame}. Please choose from the list.")
                raise ValueError("Invalid output device selection")
        except ValueError:
            print(f"Invalid input: '{selected_output_idx_str}'. Please enter a number.")
            # Handle error, e.g., exit or default
            raise # Or set a default / re-prompt

    p.terminate() # Terminate PyAudio instance
    # pygame.quit() # Not here, as pygame.mixer.init will be called later in globals

    print(f"\n✅ Selected Input (PyAudio): #{config.PYAUDIO_INPUT_DEVICE_INDEX}")
    if config.PYAUDIO_OUTPUT_DEVICE_NAME:
        print(f"✅ Selected Output (Pygame): #{config.PYAUDIO_OUTPUT_DEVICE_INDEX} - {config.PYAUDIO_OUTPUT_DEVICE_NAME}")
    else:
        print("⚠️ No output device selected/available for Pygame.")
