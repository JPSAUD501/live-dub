import time
from . import config
from . import globals # app_globals is an alias in main.py, here it's just globals
from .audio_processing import play_audio_pygame, generate_audio_tts, transcribe_segment
from .translation import translate_with_mini

def playback_worker_thread_func():
    print("🔊 [PLAYBACK_Q] Playback Worker: Started.")
    expected_segment_id = 0
    pending_play_buffer = {} # segment_id -> audio_data

    while not globals.done:
        try:
            item = globals.audio_bytes_to_playback_queue.get(timeout=1)
            if item is None: # Sentinel for shutdown
                globals.audio_bytes_to_playback_queue.task_done()
                break # Exit the loop, then try to play pending items

            segment_id, audio_data_to_play = item

            if segment_id == expected_segment_id:
                if audio_data_to_play:
                    print(f"🔊 [PLAYBACK_AUDIO] Playing segment {segment_id}.")
                    play_audio_pygame(audio_data_to_play)
                else:
                    print(f"🔊 [PLAYBACK_AUDIO] Segment {segment_id} has no audio data. Skipping playback.")
                expected_segment_id += 1
                
                # Process pending buffer for contiguous segments
                while expected_segment_id in pending_play_buffer:
                    buffered_audio = pending_play_buffer.pop(expected_segment_id)
                    if buffered_audio:
                        print(f"🔊 [PLAYBACK_AUDIO] Playing buffered segment {expected_segment_id}.")
                        play_audio_pygame(buffered_audio)
                    else:
                        print(f"🔊 [PLAYBACK_AUDIO] Buffered segment {expected_segment_id} has no audio data. Skipping playback.")
                    expected_segment_id += 1
            elif segment_id > expected_segment_id:
                print(f"🔊 [PLAYBACK_Q] Buffering segment {segment_id} (expected {expected_segment_id}).")
                pending_play_buffer[segment_id] = audio_data_to_play
            else: # segment_id < expected_segment_id
                print(f"⚠️ [PLAYBACK_Q] Received segment {segment_id} which is older than expected {expected_segment_id}. Discarding.")
            
            globals.audio_bytes_to_playback_queue.task_done()
        except globals.queue.Empty:
            continue 
        except Exception as e:
            print(f"⚠️ [PLAYBACK_Q] Playback Worker: Error: {e}")
            # Ensure task_done is called if item was dequeued before error
            if 'item' in locals() and item is not None: # Check if item was successfully dequeued
                 globals.audio_bytes_to_playback_queue.task_done()
    
    # Shutdown: Try to play any remaining buffered audio in order
    print("🔊 [PLAYBACK_Q] Worker loop ended. Processing any remaining buffered audio...")
    sorted_pending_ids = sorted(pending_play_buffer.keys())
    for seg_id in sorted_pending_ids:
        if seg_id == expected_segment_id:
            buffered_audio = pending_play_buffer.pop(seg_id)
            if buffered_audio:
                print(f"🔊 [PLAYBACK_AUDIO] Playing buffered segment {seg_id} post-loop.")
                play_audio_pygame(buffered_audio)
            else:
                print(f"🔊 [PLAYBACK_AUDIO] Buffered segment {seg_id} post-loop has no audio. Skipping playback.")
            expected_segment_id += 1
        elif seg_id > expected_segment_id:
            print(f"🔊 [PLAYBACK_Q] Gap detected at shutdown. Cannot play segment {seg_id}, expected {expected_segment_id}. Remaining buffered: {list(pending_play_buffer.keys())}")
            break # Stop if there's a gap, as order cannot be maintained

    if pending_play_buffer:
        print(f"⚠️ [PLAYBACK_Q] Playback Worker stopped with unplayed buffered segments: {list(pending_play_buffer.keys())}")
    
    print("🔊 [PLAYBACK_Q] Playback Worker: Stopped.")


def audio_generation_worker_thread_func():
    print("🎶 [TTS_Q] Audio Generation Worker: Started.")
    while not globals.done:
        try:
            item = globals.text_to_speech_queue.get(timeout=1)
            if item is None: # Sentinel
                globals.text_to_speech_queue.task_done()
                globals.audio_bytes_to_playback_queue.put(None) # Signal playback worker
                break
            
            segment_id, text_to_speak = item
            
            audio_data = None # Initialize audio_data to None
            if config.TTS_OUTPUT_ENABLED and text_to_speak and text_to_speak.strip():
                print(f"🎤 [TTS_GEN_TASK] ({config.TTS_PROVIDER}) Segment {segment_id}: Synthesizing audio for: \"{text_to_speak}\"")
                audio_data = generate_audio_tts(text_to_speak)
            
            # Always put something to maintain sequence, even if it's None for audio_data
            globals.audio_bytes_to_playback_queue.put((segment_id, audio_data))
            globals.text_to_speech_queue.task_done()
        except globals.queue.Empty:
            continue
        except Exception as e:
            print(f"⚠️ [TTS_Q] Audio Generation Worker: Error: {e}")
            if 'item' in locals() and item is not None:
                globals.text_to_speech_queue.task_done()
    print("🎶 [TTS_Q] Audio Generation Worker: Stopped.")


def translation_worker_thread_func():
    print("📚 [TRANSLATION_Q] Translation Worker: Started.")
    while not globals.done:
        try:
            item = globals.transcription_to_translation_queue.get(timeout=1)
            if item is None: # Sentinel
                globals.transcription_to_translation_queue.task_done()
                globals.text_to_speech_queue.put(None) # Signal audio gen worker
                break

            segment_id, sdk_text, text_4o = item

            # Store final 4o transcriptions if it's not empty
            command_text = text_4o if text_4o and text_4o.strip() else sdk_text
            if command_text and command_text.strip(): # command_text might be None if both inputs are None/empty
                globals.all_results.append(command_text)
            
            translated_phrases_list = translate_with_mini(sdk_text, text_4o)

            log_text = " ".join(translated_phrases_list) if translated_phrases_list else "[No new translation]"
            print(f"✅ [TRANSLATE_LLM_RESULT] Segment {segment_id}: \"{log_text}\"")

            text_to_speak = " ".join(translated_phrases_list)
            # Pass segment_id along, even if text_to_speak is empty, to maintain sequence
            globals.text_to_speech_queue.put((segment_id, text_to_speak if text_to_speak.strip() else ""))
            
            globals.transcription_to_translation_queue.task_done()
        except globals.queue.Empty:
            continue
        except Exception as e:
            print(f"⚠️ [TRANSLATION_Q] Translation Worker: Error: {e}")
            if 'item' in locals() and item is not None:
                 globals.transcription_to_translation_queue.task_done()
    print("📚 [TRANSLATION_Q] Translation Worker: Stopped.")


def periodic_transcription_thread_func():
    print(f"⏱️ [{config.TRANSCRIPTION_PROVIDER}_PERIODIC_TRANSCRIBE] Periodic Transcription Worker: Started.")
    while not globals.done:
        if globals.speech_active.is_set(): # Only run if speech is active
            current_time = time.monotonic()
            if globals.utterance_start_time_monotonic is not None and \
               (current_time - globals.last_periodic_transcription_time >= config.PERIODIC_TRANSCRIPTION_INTERVAL_S):
                
                audio_segment_periodic = b""
                sdk_text_snapshot = globals.current_sdk_interim_text 

                overlap_bytes = int(config.PYAUDIO_RATE *
                                    (config.PERIODIC_TRANSCRIPTION_OVERLAP_MS / 1000) *
                                    config.PYAUDIO_SAMPLE_WIDTH *
                                    config.PYAUDIO_CHANNELS)
                
                desired_start = max(globals.utterance_audio_start_byte_offset,
                                    globals.last_periodic_transcription_byte_offset - overlap_bytes)

                with globals.audio_buffer_lock:
                    if 0 <= desired_start < len(globals.full_audio_data):
                        audio_segment_periodic = globals.full_audio_data[desired_start : len(globals.full_audio_data)]
                    elif len(globals.full_audio_data) > 0 and globals.utterance_audio_start_byte_offset >= len(globals.full_audio_data):
                        print(f"⚠️ [{config.TRANSCRIPTION_PROVIDER}_PERIODIC_TRANSCRIBE] Warning: utterance_audio_start_byte_offset ({globals.utterance_audio_start_byte_offset}) invalid with buffer len {len(globals.full_audio_data)}. Using full buffer.")
                        audio_segment_periodic = globals.full_audio_data[:] 

                if audio_segment_periodic:
                    segment_id = globals.get_next_segment_id()
                    print(f"\n🧠 [{config.TRANSCRIPTION_PROVIDER}_TRANSCRIBE_TASK] Segment {segment_id}: Periodically transcribing audio segment...")
                    text_4o_periodic = transcribe_segment(audio_segment_periodic)
                    print(f"🧠 [{config.TRANSCRIPTION_PROVIDER}_TRANSCRIBE_RESULT] Segment {segment_id}: Periodic transcription: \"{text_4o_periodic}\"")

                    if text_4o_periodic.strip() or sdk_text_snapshot.strip():
                        globals.transcription_to_translation_queue.put((segment_id, sdk_text_snapshot, text_4o_periodic))
                    else:
                        print(f"ℹ️ [{config.TRANSCRIPTION_PROVIDER}_PERIODIC_TRANSCRIBE] Segment {segment_id}: Skipping enqueue as both SDK snapshot and 4o text are empty.")
                else:
                    pass 

                globals.last_periodic_transcription_byte_offset = len(globals.full_audio_data)
                globals.last_periodic_transcription_time = current_time
            
            time.sleep(0.1) 
        else:
            time.sleep(0.2) 

    print(f"⏱️ [{config.TRANSCRIPTION_PROVIDER}_PERIODIC_TRANSCRIBE] Periodic Transcription Worker: Stopped.")
