"""The course LLM (Gemma 4 31B, served by Open WebUI): its settings and the client.

The API key is read from the LLM_API_KEY environment variable, so it is never written
in the code and cannot be committed by mistake.
"""
import json
import os

from openai import APIError, OpenAI

LLM_BASE_URL = "https://openwebui.ux.uis.no/api"
LLM_MODEL = "gorina10.gemma-4-31b"

# A reply must come back within 3-5 s, so one call may not hang for longer than this.
# A timed-out call is not retried, so a stuck server costs at most 5 s.
# To be checked against the real ms per call in `python -m musiccrs.checks.check_nlu`.
LLM_TIMEOUT_SECONDS = 5

# Sent when the model's answer had no valid JSON, before the second (last) call.
RETRY_MESSAGE = "That was not valid JSON. Answer again with the JSON object only."


def create_client():
    """An OpenAI client for the course LLM, or None when LLM_API_KEY is not set.

    LLM_API_KEY="sk-123"  -> OpenAI(api_key="sk-123", base_url=LLM_BASE_URL)
    no LLM_API_KEY        -> None (the agent then runs with slash commands only)
    """
    # os.environ.get gives "" when the variable does not exist.
    api_key = os.environ.get("LLM_API_KEY", "")
    api_key = api_key.strip()
    if api_key == "":
        return None
    # max_retries=0: the openai library would otherwise retry failed calls on its own
    # (2 extra calls by default). ask_json decides about retries itself.
    return OpenAI(api_key=api_key, base_url=LLM_BASE_URL, max_retries=0)


def extract_json(text):
    """The JSON object inside the model's answer, as a dict, or None if there is none.

    '{"intent": "SHOW"}'                         -> {"intent": "SHOW"}
    '```json\\n{"intent": "SHOW"}\\n```'           -> {"intent": "SHOW"}
    'Sure! {"intent": "SHOW"} Hope this helps.'  -> {"intent": "SHOW"}
    '{"intent": "SHOW",}'                        -> None (broken JSON)
    'I am not sure.'                             -> None
    """
    if text is None:
        return None

    # The object runs from the first "{" to the last "}". Cutting there also drops
    # the ```json fences and any words the model writes around the object.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        return None
    json_text = text[start:end + 1]

    # json.loads raises JSONDecodeError when the text is not valid JSON.
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return None
    return data


def ask_json(llm, messages):
    """Send the messages to the LLM and return the JSON object in its answer, or None.

    messages = [{"role": "system", "content": "... Answer with JSON only ..."},
                {"role": "user", "content": "add hotel california"}]
    -> {"intent": "ADD", "slots": {"track": "hotel california"}}

    Temperature 0, so the same message always gets the same answer.
    No valid JSON -> the model sees its answer and is asked once more (2 calls at most).
    Still no JSON, or a network/API error -> None, so the agent never crashes on the LLM.
    """
    # A copy, so the retry messages are not added to the caller's list.
    current_messages = list(messages)

    for call_number in range(2):
        try:
            response = llm.chat.completions.create(
                model=LLM_MODEL,
                messages=current_messages,
                temperature=0,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except APIError as error:
            # APIError covers a wrong key, a server error, no connection and a timeout.
            print("LLM call failed:", error)
            return None

        answer = response.choices[0].message.content
        data = extract_json(answer)
        if data is not None:
            return data

        # No valid JSON: show the model its own answer and ask again.
        if answer is None:
            answer = ""
        current_messages.append({"role": "assistant", "content": answer})
        current_messages.append({"role": "user", "content": RETRY_MESSAGE})

    return None
