import time
import queue  # For queue.Empty

from . import config_new as config
from . import globals_new as app_globals
from .audio_utils_new import transcribe_with_scribe
from .llm_utils_new import llm_translate_and_decide_speech

def periodic_scribe_transcription_worker_new():
    """Worker thread that periodically sends audio chunks to Scribe for transcription"""
    print(f"⏱️ [SCRIBE_PERIODIC] Worker: Started. Interval: {config.PERIODIC_SCRIBE_INTERVAL_S}s, Pre-roll: {config.PERIODIC_SCRIBE_PRE_ROLL_MS}ms.")
    last_debug_time = time.monotonic()
    
    while not app_globals.done.is_set():
        current_time = time.monotonic()
        
        # Print periodic debug info even when speech is not active
        if current_time - last_debug_time >= 10.0:  # Every 10 seconds
            last_debug_time = current_time
            
        if app_globals.speech_active.is_set():
            if app_globals.utterance_start_time_monotonic is not None and \
               (current_time - app_globals.last_periodic_scribe_submission_time >= config.PERIODIC_SCRIBE_INTERVAL_S):
                
                print(f"⏱️ [SCRIBE_PERIODIC_TIME] Time to transcribe! Last transcription was {current_time - app_globals.last_periodic_scribe_submission_time:.2f}s ago")
                
                audio_segment_pcm_periodic = b""
                current_chunk_start_byte = 0
                current_chunk_end_byte = 0
                
                with app_globals.audio_buffer_lock:
                    current_buffer_len = len(app_globals.full_audio_data)
                    pre_roll_bytes = int(config.PYAUDIO_RATE * (config.PERIODIC_SCRIBE_PRE_ROLL_MS / 1000) * \
                                        config.PYAUDIO_SAMPLE_WIDTH * config.PYAUDIO_CHANNELS)
                    
                    # Use last offset as reference, but ensure we get at least the specified pre-roll
                    start_byte = max(app_globals.utterance_audio_start_byte_offset,
                                    app_globals.last_periodic_scribe_chunk_end_byte_offset - pre_roll_bytes)
                    
                    # Ensure we don't exceed buffer length
                    start_byte = min(start_byte, current_buffer_len)
                    end_byte = current_buffer_len

                    if start_byte < end_byte and end_byte > 0:
                        audio_segment_pcm_periodic = app_globals.full_audio_data[start_byte:end_byte]
                        current_chunk_start_byte = start_byte
                        current_chunk_end_byte = end_byte
                    else:
                        print(f"⚠️ [SCRIBE_PERIODIC_ERROR] Invalid byte range: {start_byte} to {end_byte}")

                if audio_segment_pcm_periodic:
                    transcribed_text_periodic = transcribe_with_scribe(audio_segment_pcm_periodic)
                    
                    if transcribed_text_periodic and not transcribed_text_periodic.startswith("[Scribe Error:"):
                        print(f"⏱️ [SCRIBE_PERIODIC_RESULT] Transcription: \"{transcribed_text_periodic}\"")
                        app_globals.scribe_to_translator_llm_queue.put(transcribed_text_periodic)
                        if app_globals.all_scribe_transcriptions_log is not None:
                            app_globals.all_scribe_transcriptions_log.append(f"[PERIODIC] {transcribed_text_periodic}")
                            
                        # Store in recent transcriptions deque
                        with app_globals.recent_scribe_transcriptions_lock:
                            app_globals.recent_scribe_transcriptions.append(transcribed_text_periodic)
                    elif transcribed_text_periodic.startswith("[Scribe Error:"):
                         print(f"⚠️ [SCRIBE_PERIODIC_ERROR] {transcribed_text_periodic}")
                    else:
                         print(f"⚠️ [SCRIBE_PERIODIC_EMPTY] Empty or invalid transcription result")
                else:
                    print("⚠️ [SCRIBE_PERIODIC_SKIP] No audio data to transcribe")
                
                # Always update timing even if we didn't get audio
                # This prevents getting stuck in a loop if audio extraction fails
                app_globals.last_periodic_scribe_submission_time = current_time
                if current_chunk_end_byte > app_globals.last_periodic_scribe_chunk_end_byte_offset:
                    app_globals.last_periodic_scribe_chunk_end_byte_offset = current_chunk_end_byte
            
            time.sleep(0.1)
        else:
            time.sleep(0.2)

    print(f"⏱️ [SCRIBE_PERIODIC] Worker: Stopped.")


def translator_llm_agent_worker_new():
    """Worker thread that processes transcriptions and decides when and what to translate"""
    print("🤖 [TRANSLATOR_LLM_AGENT] Worker: Started.")
    # Initialize recent_scribe_transcriptions deque with correct maxlen from config
    if not isinstance(app_globals.recent_scribe_transcriptions, queue.deque) or \
       app_globals.recent_scribe_transcriptions.maxlen != config.LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE:
        app_globals.recent_scribe_transcriptions = queue.deque(maxlen=config.LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE)

    while not app_globals.done.is_set():
        try:
            new_scribe_fragment = app_globals.scribe_to_translator_llm_queue.get(timeout=1)
            if new_scribe_fragment is None:  # Sentinel for shutdown
                app_globals.scribe_to_translator_llm_queue.task_done()
                break
            
            with app_globals.recent_scribe_transcriptions_lock:
                current_recent_fragments = list(app_globals.recent_scribe_transcriptions)
            
            with app_globals.translated_speech_history_lock:
                current_translated_history = list(app_globals.translated_speech_history)
            with app_globals.native_speech_history_processed_by_llm_lock:
                current_native_processed_history = list(app_globals.native_speech_history_processed_by_llm)

            llm_decision = llm_translate_and_decide_speech(
                current_recent_fragments,
                current_translated_history,
                current_native_processed_history
            )

            if llm_decision.get("should_speak"):
                text_to_speak = llm_decision.get("text_to_speak", "")
                processed_original = llm_decision.get("newly_transcribed_segment_processed", "")

                if text_to_speak:
                    print(f"🗣️ [TRANSLATOR_LLM_SAYS]: \"{text_to_speak}\"")
                    # (Playback logic can be added in a future implementation)

                    with app_globals.translated_speech_history_lock:
                        app_globals.translated_speech_history.append(text_to_speak)
                        # Keep the history within size limits
                        if len(app_globals.translated_speech_history) > 50: 
                            app_globals.translated_speech_history = app_globals.translated_speech_history[-50:]
                
                if processed_original and not processed_original.startswith("[LLM Error]"):
                    with app_globals.native_speech_history_processed_by_llm_lock:
                        app_globals.native_speech_history_processed_by_llm.append(processed_original)
                        # Keep the history within size limits
                        if len(app_globals.native_speech_history_processed_by_llm) > 50: 
                            app_globals.native_speech_history_processed_by_llm = app_globals.native_speech_history_processed_by_llm[-50:]
            
            app_globals.scribe_to_translator_llm_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"⚠️ [TRANSLATOR_LLM_AGENT_ERROR] Worker error: {e} (Type: {type(e).__name__})")
            if 'new_scribe_fragment' in locals() and new_scribe_fragment is not None:
                try:
                    app_globals.scribe_to_translator_llm_queue.task_done()
                except ValueError:
                    pass
    print("🤖 [TRANSLATOR_LLM_AGENT] Worker: Stopped.")
