import json
from . import config
from . import globals

def translate_with_mini(sdk_text: str, transcription_input: str) -> list[str]:
    system_prompt = f"""
You are a highly specialized real-time translation AI, converting spoken {config.INPUT_LANGUAGE_NAME_FOR_PROMPT} into {config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT}. Your primary goal is to provide accurate, natural-sounding translations of ONLY NEW and COMPLETE segments of speech.

# CRITICAL INPUTS YOU WILL RECEIVE IN THE JSON PAYLOAD:
1.  `transcription`: This is the current, potentially ongoing, speech transcription in {config.INPUT_LANGUAGE_NAME_FOR_PROMPT}. It may contain complete sentences, partial phrases, or fragments, especially towards the end if the speaker is still talking.
2.  `translated_history`: (Sent as "history" in the payload) A log of what has ALREADY BEEN TRANSLATED into {config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT} and SPOKEN by the system. Use this to ensure your new translation provides continuity and avoids repeating already spoken translated phrases.
3.  `original_language_speech_history`: A log of the {config.INPUT_LANGUAGE_NAME_FOR_PROMPT} text that has ALREADY BEEN IDENTIFIED AS SPOKEN, COMPLETE, AND PROCESSED by you in previous turns. This is your primary reference to determine what part of the current `transcription` is new.

# YOUR TASK:
Your main job is to:
1. Identify the NEW, SEMANTICALLY COMPLETE segment from the `transcription` by comparing it against the `original_language_speech_history`. This identified segment is `newly_translatable_complete_segment_original`.
2. Translate ONLY this `newly_translatable_complete_segment_original` into {config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT}. This becomes `newly_translated_complete_segment_speech`.
3. Ensure this new translation flows naturally with the `translated_history` and does not repeat content already present in it.
4. Structure your findings into the specified JSON format.

# RULES FOR IDENTIFYING THE "NEWLY TRANSLATABLE COMPLETE SEGMENT":
1.  **Differential Analysis based on Original Language**: Compare the meaning of `transcription` (in {config.INPUT_LANGUAGE_NAME_FOR_PROMPT}) against `original_language_speech_history` (also in {config.INPUT_LANGUAGE_NAME_FOR_PROMPT}) to determine what part of `transcription` is genuinely new.
2.  **Completeness is Paramount**: From the new part of `transcription`, you MUST extract only coherent, grammatically complete sentences or phrases for `newly_translatable_complete_segment_original`.
    *   If the newest part of `transcription` is a fragment (e.g., "and then he went to the...") do NOT include this fragment. Wait for it to be completed in a subsequent call.
    *   The `newly_translatable_complete_segment_original` MUST NOT end with ellipses (...) suggesting incompleteness you introduced. It must be a self-contained, complete thought.
3.  **Empty if Nothing New or Incomplete**: If all of `transcription` is covered by `original_language_speech_history`, OR if the new part of `transcription` is just an incomplete fragment, then `newly_translatable_complete_segment_original` (and consequently `newly_translated_complete_segment_speech`) MUST be an empty string.
4.  **Non-Speech Content**: Ignore parenthetical non-speech sounds (e.g., "(laughter)", "(music)") and error messages (e.g., "[Error: ...]") within `transcription`. If `transcription` consists only of these, `newly_translatable_complete_segment_original` is empty.
5.  **Handling Evolving Transcriptions (Refinements)**:
    a. The `transcription` input may be a refined or more complete version of speech segments that were partially covered or differently phrased in `original_language_speech_history` (e.g., a final transcription after periodic ones).
    b. Your primary goal is to identify the segment of `transcription` that introduces genuinely *new* semantic information not yet adequately covered by `original_language_speech_history`.
    c. If `transcription` begins with new information and then continues into phrases that are semantically equivalent to (even if slightly rephrased or more detailed than) content in `original_language_speech_history`, the `newly_translatable_complete_segment_original` should ideally be ONLY the initial new part that precedes the already-covered semantic content.
    d. Example:
        `original_language_speech_history`: "...payment will be made if the amount is over 5%."
        `transcription`: "The company announced that payment will be made if the agreed amount is over five percent, according to the agreement."
        Ideal `newly_translatable_complete_segment_original`: "The company announced that" 
        (This is because the rest, "payment will be made if the agreed amount is over five percent, according to the agreement," is a refinement of what's in history, not entirely new information).
    e. However, if a refinement in `transcription` constitutes a significant correction, adds crucial new details that alter the core meaning of the historical part, or provides a much earlier coherent starting point to a previously fragmented idea, you may identify a larger segment from `transcription` as new. Strive for a balance that ensures all new information is captured while minimizing perceptible redundancy in the translated speech output.

# JSON OUTPUT FORMAT (MANDATORY):
You MUST respond exclusively with a JSON object containing exactly these two string properties:

```json
{{
  "newly_translatable_complete_segment_original": "The NEW, COMPLETE, and coherent segment from `transcription` (in {config.INPUT_LANGUAGE_NAME_FOR_PROMPT}) that you've identified for translation. This MUST be empty if no new complete segment is found or if the new part is a fragment.",
  "newly_translated_complete_segment_speech": "The accurate and natural translation of `newly_translatable_complete_segment_original` into {config.OUTPUT_LANGUAGE_NAME_FOR_PROMPT}. THIS IS THE CRITICAL OUTPUT FOR SPEECH. It MUST be an empty string if `newly_translatable_complete_segment_original` is empty. Do not use ellipses (...) here to indicate omission."
}}
```

# EXAMPLES:

## Example 1: New Speech
`transcription`: "Olá, como você está hoje? Acho que vou ao parque."
`translated_history`: "" (empty)
`original_language_speech_history`: "" (empty)
Expected JSON:
```json
{{
  "newly_translatable_complete_segment_original": "Olá, como você está hoje? Acho que vou ao parque.",
  "newly_translated_complete_segment_speech": "Hello, how are you today? I think I'll go to the park."
}}
```

## Example 2: Continuation of Speech
`transcription`: "O tempo está bom. Eu vou dar uma caminhada e talvez tomar um sorvete."
`translated_history`: "The weather is nice."
`original_language_speech_history`: "O tempo está bom."
Expected JSON:
```json
{{
  "newly_translatable_complete_segment_original": "Eu vou dar uma caminhada e talvez tomar um sorvete.",
  "newly_translated_complete_segment_speech": "I'm going for a walk and maybe get some ice cream."
}}
```

## Example 3: Transcription contains incomplete new part
`transcription`: "Eu gosto de programar em Python e também estou aprendendo sobre..." (speaker trails off or segment is cut)
`translated_history`: "I like to program in Python."
`original_language_speech_history`: "Eu gosto de programar em Python."
Expected JSON:
```json
{{
  "newly_translatable_complete_segment_original": "",
  "newly_translated_complete_segment_speech": ""
}}
```
(Note: `newly_translatable_complete_segment_original` is empty because "e também estou aprendendo sobre..." is incomplete. Consequently, `newly_translated_complete_segment_speech` is also empty.)

## Example 4: Transcription is fully covered by history
`transcription`: "Obrigado."
`translated_history`: "Thank you."
`original_language_speech_history`: "Obrigado."
Expected JSON:
```json
{{
  "newly_translatable_complete_segment_original": "",
  "newly_translated_complete_segment_speech": ""
}}
```
Remember: Accuracy, natural flow, and adherence to the "complete new segment" rule are paramount.
"""
    user_payload = {
        "transcription": transcription_input,
        "history": globals.translated_output_history, # This is the translated_history
        "original_language_speech_history": globals.original_speech_history
    }
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
    ]
    if not config.client_az_translation:
        print("⚠️ Translation LLM: Client not initialized.")
        return ["[Translation Error: Client not initialized]"]

    new_translation_to_speak = ""
    raw_llm_response_content = None # For logging

    try:
        resp = config.client_az_translation.chat.completions.create(
            model=config.AZ_TRANSLATION_MODEL,
            messages=messages,
            temperature=0.1, # Slightly lower for more deterministic structured output
            response_format={"type": "json_object"} # Request JSON output
        )
        raw_llm_response_content = resp.choices[0].message.content

        if raw_llm_response_content is None:
            print("⚠️ Translation LLM: API returned None content.")
            new_translation_to_speak = "[Translation Error: API returned None]"
        elif not isinstance(raw_llm_response_content, str):
            print(f"⚠️ Translation LLM: API returned non-string content: {type(raw_llm_response_content)}. Value: {raw_llm_response_content}")
            new_translation_to_speak = "[Translation Error: API returned non-string]"
        else:
            try:
                json_response = json.loads(raw_llm_response_content)
                if isinstance(json_response, dict):
                    # Extract segments based on the new simplified JSON structure
                    ntcs_original = json_response.get("newly_translatable_complete_segment_original")
                    extracted_segment_for_speech = json_response.get("newly_translated_complete_segment_speech")
                    
                    log_message = (
                        f"📝 [TRANSLATION_LLM_IO]\n"
                        f"  ├─ Input Transcription (raw for LLM): \"{transcription_input}\"\n"
                        f"  ├─ Input Translated History (for LLM): \"{globals.translated_output_history[-200:]}... (last 200 chars)\"\n"
                        f"  ├─ Input Original Speech History (for LLM): \"{globals.original_speech_history[-200:]}... (last 200 chars)\"\n"
                        f"  ├─ Raw LLM Response JSON:\n{json.dumps(json_response, indent=2, ensure_ascii=False)}\n"
                        f"  ├─ Extracted Original Segment (for history update): \"{ntcs_original}\"\n"
                        f"  └─ Extracted for Speech (translated): \"{extracted_segment_for_speech}\""
                    )
                    print(log_message)

                    if extracted_segment_for_speech is None:
                        # Also check ntcs_original as it's part of the expected pair
                        missing_keys = []
                        if extracted_segment_for_speech is None:
                            missing_keys.append("'newly_translated_complete_segment_speech'")
                        if ntcs_original is None:
                             missing_keys.append("'newly_translatable_complete_segment_original'")
                        
                        error_msg_detail = f"{', '.join(missing_keys)} missing in JSON response: {raw_llm_response_content}"
                        print(f"⚠️ Translation LLM: {error_msg_detail}")
                        new_translation_to_speak = f"[Translation Error: {', '.join(missing_keys)} missing]"

                    elif not isinstance(extracted_segment_for_speech, str) or \
                         (ntcs_original is not None and not isinstance(ntcs_original, str)): # ntcs_original can be None if key missing, but if present, must be str
                        
                        type_errors = []
                        if not isinstance(extracted_segment_for_speech, str):
                            type_errors.append(f"'newly_translated_complete_segment_speech' is not a string (type: {type(extracted_segment_for_speech).__name__})")
                        if ntcs_original is not None and not isinstance(ntcs_original, str):
                            type_errors.append(f"'newly_translatable_complete_segment_original' is not a string (type: {type(ntcs_original).__name__})")
                        
                        error_msg_detail = f"{'; '.join(type_errors)}. Response: {raw_llm_response_content}"
                        print(f"⚠️ Translation LLM: {error_msg_detail}")
                        new_translation_to_speak = f"[Translation Error: Type error in JSON fields]"
                    else:
                        new_translation_to_speak = extracted_segment_for_speech # This is the string we want for TTS
                        # ntcs_original is now correctly populated here if valid

                else:
                    print(f"⚠️ Translation LLM: Unexpected JSON format (not a dict): {raw_llm_response_content}")
                    new_translation_to_speak = f"[Translation Error: Unexpected JSON root type ({type(json_response).__name__})]"
            except json.JSONDecodeError:
                print(f"⚠️ Translation LLM: Response is not valid JSON: {raw_llm_response_content}")
                # Fallback: try to use the raw content if it seems like a simple phrase and not an error message itself
                if raw_llm_response_content.startswith("[") and raw_llm_response_content.endswith("]"):
                     new_translation_to_speak = raw_llm_response_content # Treat as error
                else:
                     new_translation_to_speak = raw_llm_response_content # Treat as direct translation attempt
            except TypeError as te_json:
                print(f"⚠️ Translation LLM: TypeError during JSON processing: {te_json}. Content: {raw_llm_response_content}")
                new_translation_to_speak = f"[Translation Error: TypeError in JSON processing - {str(te_json)}]"
        
    except TypeError as te_api:
        print(f"⚠️ Translation LLM: TypeError from API or response handling: {te_api}. Response content: {raw_llm_response_content if raw_llm_response_content else 'N/A'}")
        new_translation_to_speak = f"[Translation Error: TypeError - {str(te_api)}]"
    except Exception as e:
        print(f"⚠️ Translation LLM: Error in API call: {e} (Type: {type(e).__name__}). Response content: {raw_llm_response_content if raw_llm_response_content else 'N/A'}")
        new_translation_to_speak = f"[Translation Error: {type(e).__name__}]"

    # Update history based on original input text (sdk_text)
    # This history is of the source language, used for context in some scenarios, not directly by the LLM's `history` param.
    globals.translation_history += sdk_text + " "
    if len(globals.translation_history) > config.MAX_TRANSLATION_HISTORY_CHARS:
        globals.translation_history = globals.translation_history[-config.MAX_TRANSLATION_HISTORY_CHARS:]

    # Update translated output history (used as `history` for the LLM)
    # and original speech history.
    if isinstance(new_translation_to_speak, str) and new_translation_to_speak.strip() and not new_translation_to_speak.startswith("[Translation Error:"):
        globals.translated_output_history += new_translation_to_speak + " "
        if len(globals.translated_output_history) > config.MAX_TRANSLATION_HISTORY_CHARS:
            globals.translated_output_history = globals.translated_output_history[-config.MAX_TRANSLATION_HISTORY_CHARS:]

        # Update original_speech_history with the corresponding original segment
        # ntcs_original is now directly from json_response.get("newly_translatable_complete_segment_original")
        # It would have been validated for type if present, or be None if missing (handled by error above)
        if ntcs_original and isinstance(ntcs_original, str) and ntcs_original.strip(): # Ensure it's a non-empty string
            globals.original_speech_history += ntcs_original + " "
            if len(globals.original_speech_history) > config.MAX_TRANSLATION_HISTORY_CHARS:
                globals.original_speech_history = globals.original_speech_history[-config.MAX_TRANSLATION_HISTORY_CHARS:]
            
    elif isinstance(new_translation_to_speak, str) and new_translation_to_speak.startswith("[Translation Error:"):
        # Do not add LLM's own error messages to the spoken history
        pass
    elif isinstance(new_translation_to_speak, str) and not new_translation_to_speak.strip():
        # This is an empty or whitespace-only string, valid, but nothing to add to history or log as an error.
        pass
    else:
        # This case handles non-string types or other unexpected scenarios
        print(f"⚠️ Translation LLM: new_translation_to_speak is of unexpected type or state before history update: '{new_translation_to_speak}' (Type: {type(new_translation_to_speak).__name__}). Skipping translated_output_history update.")

    # Return format expected by downstream: list of strings.
    # If new_translation_to_speak is a valid, non-empty, non-error string, wrap it in a list.
    # Otherwise, return an empty list or a list containing the error.
    if isinstance(new_translation_to_speak, str) and new_translation_to_speak.strip():
        if new_translation_to_speak.startswith("[Translation Error:"):
            return [new_translation_to_speak] # Return error as a list item
        return [new_translation_to_speak] # Return the good translation string in a list
    elif isinstance(new_translation_to_speak, str) and not new_translation_to_speak.strip():
        return [] # Empty string means nothing new to say
    else: # Should be an error string already
        return [str(new_translation_to_speak)] # Fallback, ensure it's a list of string
