import time
import queue  # For queue.Empty

import config as config
import globals as app_globals
from audio_utils import transcribe_with_scribe, generate_audio_elevenlabs, play_audio_pygame
from llm_utils import llm_translate_and_decide_speech

def periodic_scribe_transcription_worker_new():
    """Worker thread that periodically sends audio chunks to Scribe for transcription"""
    print(f"⏱️ [SCRIBE_PERIODIC] Worker: Started. Interval: {config.PERIODIC_SCRIBE_INTERVAL_S}s, Inter-Chunk Overlap: {config.PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS}ms.")
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
                
                audio_segment_periodic = b""
                start_byte_this_chunk = 0
                end_byte_current_chunk = 0

                with app_globals.audio_buffer_lock:
                    current_buffer_len = len(app_globals.full_audio_data)
                    
                    inter_chunk_overlap_bytes = int(config.PYAUDIO_RATE * 
                                                     (config.PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS / 1000) * 
                                                     config.PYAUDIO_SAMPLE_WIDTH * config.PYAUDIO_CHANNELS)
                    
                    # Determine the start byte for the current periodic segment
                    # If it's the first segment of the utterance, it starts at utterance_audio_start_byte_offset.
                    # Otherwise, it starts 'inter_chunk_overlap_bytes' before the end of the previous segment.
                    start_byte = max(app_globals.utterance_audio_start_byte_offset,
                                     app_globals.last_periodic_scribe_chunk_end_byte_offset - inter_chunk_overlap_bytes)
                    
                    # Ensure we don't exceed buffer length
                    start_byte = min(start_byte, current_buffer_len)
                    end_byte = current_buffer_len

                    if start_byte < end_byte and end_byte > 0:
                        audio_segment_periodic = app_globals.full_audio_data[start_byte:end_byte]
                        start_byte_this_chunk = start_byte
                        end_byte_current_chunk = end_byte
                        app_globals.last_periodic_scribe_chunk_end_byte_offset = end_byte  # Update immediately
                    else:
                        print(f"⚠️ [SCRIBE_PERIODIC_ERROR] Invalid byte range: {start_byte} to {end_byte}")

                app_globals.last_periodic_scribe_submission_time = current_time  # Update submission time

                if audio_segment_periodic:
                    transcribed_text_periodic = transcribe_with_scribe(
                        audio_segment_periodic, 
                        is_final_segment=False
                    )
                    
                    is_valid_transcription = False
                    if transcribed_text_periodic and \
                       not transcribed_text_periodic.startswith("[Scribe Error:") and \
                       "\uFFFD" not in transcribed_text_periodic:  # Filter out replacement characters
                        is_valid_transcription = True
                        if config.SCRIBE_LANGUAGE_CODE == "pt" and len(transcribed_text_periodic) < 5 and not any(c.isalpha() for c in transcribed_text_periodic):
                            is_valid_transcription = False

                    if is_valid_transcription:
                        print(f"⏱️ [SCRIBE_PERIODIC_RESULT] Transcription: \"{transcribed_text_periodic}\"")
                        app_globals.scribe_to_translator_llm_queue.put(transcribed_text_periodic)
                        if app_globals.all_scribe_transcriptions_log is not None:
                            app_globals.all_scribe_transcriptions_log.append(f"[PERIODIC] {transcribed_text_periodic}")
                            
                        # Store in recent transcriptions deque
                        with app_globals.recent_scribe_transcriptions_lock:
                            app_globals.recent_scribe_transcriptions.append(transcribed_text_periodic)
                    else:
                        if transcribed_text_periodic:  # Log if it was invalid but not empty
                            print(f"⚠️ [SCRIBE_PERIODIC_INVALID] Invalid or filtered periodic transcription: \"{transcribed_text_periodic}\"")
                else:
                    print("⚠️ [SCRIBE_PERIODIC_SKIP] No audio data to transcribe")
            
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
            # Get all available transcriptions from the queue to form a batch
            current_transcriptions_batch = []
            while not app_globals.scribe_to_translator_llm_queue.empty():
                transcription = app_globals.scribe_to_translator_llm_queue.get_nowait()
                if transcription is None:  # Sentinel for shutdown
                    app_globals.done.set()  # Propagate shutdown signal
                    break
                current_transcriptions_batch.append(transcription)
            
            if app_globals.done.is_set() and not current_transcriptions_batch:  # Check again if shutdown was signaled by None
                break

            if not current_transcriptions_batch:
                time.sleep(0.1)  # Wait if no new transcriptions
                continue

            # Update recent transcriptions deque
            with app_globals.recent_scribe_transcriptions_lock:
                for trans in current_transcriptions_batch:
                    app_globals.recent_scribe_transcriptions.append(trans)
                
                # Convert deque to list for the LLM
                llm_input_fragments = list(app_globals.recent_scribe_transcriptions)

            # Get current history (thread-safe copies within the call if needed, or manage here)
            with app_globals.translated_speech_history_lock:
                current_translated_history = list(app_globals.translated_speech_history)
            with app_globals.native_speech_history_processed_by_llm_lock:
                current_native_history = list(app_globals.native_speech_history_processed_by_llm)

            llm_response = llm_translate_and_decide_speech(
                recent_scribe_fragments=llm_input_fragments,
                current_translated_speech_history=current_translated_history,
                current_native_speech_history_processed_by_llm=current_native_history
            )

            if llm_response:
                newly_processed_original = llm_response.get("newly_transcribed_segment_processed", "")
                text_to_speak = llm_response.get("text_to_speak", "")
                should_speak = llm_response.get("should_speak", False)

                if newly_processed_original:
                    with app_globals.native_speech_history_processed_by_llm_lock:
                        app_globals.native_speech_history_processed_by_llm.append(newly_processed_original)
                        # Optional: Truncate history if it gets too long
                        if len(app_globals.native_speech_history_processed_by_llm) > config.LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE * 5:  # Example limit
                            app_globals.native_speech_history_processed_by_llm.pop(0)
                
                if should_speak and text_to_speak:
                    print(f"🗣️ [TRANSLATOR_LLM_SAYS]: \"{text_to_speak}\"")
                    with app_globals.translated_speech_history_lock:
                        app_globals.translated_speech_history.append(text_to_speak)
                        # Optional: Truncate history
                        if len(app_globals.translated_speech_history) > config.LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE * 5:
                            app_globals.translated_speech_history.pop(0)
                    
                    # --- Send to TTS queue ---
                    segment_id = app_globals.get_new_segment_id()
                    app_globals.llm_to_tts_queue.put((segment_id, text_to_speak))

        except queue.Empty:
            if app_globals.done.is_set():
                break
            time.sleep(0.1)  # Wait if queue is empty
            continue
        except Exception as e:
            print(f"⚠️ [TRANSLATOR_LLM_AGENT] Error: {e} (Type: {type(e).__name__})")
            time.sleep(1)  # Avoid rapid error looping

    print("🤖 [TRANSLATOR_LLM_AGENT] Worker: Stopped.")


def tts_worker_new():
    """Worker to generate audio from text using TTS."""
    print("🎶 [TTS_WORKER] Worker: Started.")
    app_globals.initialize_pygame_mixer_if_needed()  # Ensure mixer is ready for playback worker

    while not app_globals.done.is_set():
        try:
            item = app_globals.llm_to_tts_queue.get(timeout=0.5)
            if item is None:  # Sentinel for shutdown
                app_globals.llm_to_tts_queue.task_done()
                break
            
            segment_id, text_to_speak = item
            
            if text_to_speak and text_to_speak.strip():
                audio_bytes = generate_audio_elevenlabs(text_to_speak, segment_id)
                app_globals.tts_to_playback_queue.put((segment_id, audio_bytes))
            else:
                # If text is empty, still pass along the segment_id with None audio
                # to maintain sequence in playback worker.
                app_globals.tts_to_playback_queue.put((segment_id, None))
            
            app_globals.llm_to_tts_queue.task_done()

        except queue.Empty:
            if app_globals.done.is_set():
                break
            continue
        except Exception as e:
            print(f"⚠️ [TTS_WORKER] Error: {e}")
            # Ensure task_done is called if item was dequeued
            if 'item' in locals() and item is not None:
                 app_globals.llm_to_tts_queue.task_done()
            time.sleep(1)

    # Signal playback worker to shut down
    app_globals.tts_to_playback_queue.put(None)
    print("🎶 [TTS_WORKER] Worker: Stopped.")


def playback_worker_new():
    """Worker to play audio segments in order."""
    print("🔊 [PLAYBACK_WORKER] Worker: Started.")
    app_globals.initialize_pygame_mixer_if_needed()

    expected_segment_id = 0
    pending_playback_buffer = {}  # Stores {segment_id: audio_bytes}

    while not app_globals.done.is_set():
        try:
            item = app_globals.tts_to_playback_queue.get(timeout=0.5)
            if item is None:  # Sentinel
                app_globals.tts_to_playback_queue.task_done()
                break
            
            segment_id, audio_bytes = item

            if segment_id == expected_segment_id:
                if audio_bytes:
                    play_audio_pygame(audio_bytes, segment_id)
                expected_segment_id += 1
                
                # Play any buffered segments that are now in order
                while expected_segment_id in pending_playback_buffer:
                    buffered_audio = pending_playback_buffer.pop(expected_segment_id)
                    if buffered_audio:
                        play_audio_pygame(buffered_audio, expected_segment_id)
                    expected_segment_id += 1
            elif segment_id > expected_segment_id:
                # print(f"ℹ️ [PLAYBACK_WORKER] Buffering segment {segment_id}, expecting {expected_segment_id}.")
                pending_playback_buffer[segment_id] = audio_bytes
            else:  # segment_id < expected_segment_id (already played or skipped)
                print(f"⚠️ [PLAYBACK_WORKER] Received old segment {segment_id}, expected {expected_segment_id}. Discarding.")
            
            app_globals.tts_to_playback_queue.task_done()

        except queue.Empty:
            if app_globals.done.is_set():
                break
            continue
        except Exception as e:
            print(f"⚠️ [PLAYBACK_WORKER] Error: {e}")
            if 'item' in locals() and item is not None:
                app_globals.tts_to_playback_queue.task_done()
            time.sleep(1)
            
    # Attempt to play any remaining items in buffer if they are in order
    print("🔊 [PLAYBACK_WORKER] Shutdown: Processing remaining buffer...")
    sorted_pending_ids = sorted(pending_playback_buffer.keys())
    for seg_id in sorted_pending_ids:
        if seg_id == expected_segment_id:
            buffered_audio = pending_playback_buffer.pop(seg_id)
            if buffered_audio:
                play_audio_pygame(buffered_audio, seg_id)
            expected_segment_id += 1
        elif seg_id > expected_segment_id:
            print(f"⚠️ [PLAYBACK_WORKER] Shutdown: Gap detected. Cannot play segment {seg_id}, expected {expected_segment_id}.")
            break  # Stop if there's a gap

    if pending_playback_buffer:
        print(f"⚠️ [PLAYBACK_WORKER] Shutdown: Discarded out-of-order segments: {list(pending_playback_buffer.keys())}")

    print("🔊 [PLAYBACK_WORKER] Worker: Stopped.")
