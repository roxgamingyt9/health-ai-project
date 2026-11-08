import json
import os
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, session


load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
SYSTEM_PROMPT = (
    "You are Health & Body AI, a helpful and friendly educational assistant "
    "for health, anatomy, and fitness topics. Give clear, accurate answers, "
    "and use Markdown when helpful. Do not diagnose or replace advice from a "
    "qualified healthcare professional. Be transparent when uncertain."
)
GENERIC_REPLIES = {
    "hi": "Hi! I'm Health & Body AI. What would you like to learn about?",
    "hello": "Hello! I'm Health & Body AI. How can I help?",
    "hey": "Hey! What would you like to know about health or fitness?",
    "who are you": "I'm Health & Body AI, an educational health and fitness assistant.",
    "what is your name": "I'm Health & Body AI.",
    "who made you": "I was created by Sreehari MK as part of the Health & Body AI project.",
    "who created you": "I was created by Sreehari MK as part of the Health & Body AI project.",
}
MAX_MESSAGE_LENGTH = 10_000
MAX_HISTORY_MESSAGES = 40
CHAT_HISTORY = {}


@app.get("/")
def index():
    return send_file(os.path.join(app.root_path, "index.html"), mimetype="text/html")


@app.get("/api/history")
def get_history():
    chat_id = session.get("chat_id")
    history = CHAT_HISTORY.get(chat_id, []) if chat_id else []
    return jsonify(messages=history)


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Please send a valid JSON request."), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify(error="Enter a message before sending."), 400
    message = message.strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify(error=f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer."), 400

    chat_id = session.get("chat_id")
    if not chat_id:
        chat_id = uuid.uuid4().hex
        session["chat_id"] = chat_id
    history = CHAT_HISTORY.get(chat_id, [])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(
        item
        for item in history[-MAX_HISTORY_MESSAGES:]
        if isinstance(item, dict)
        and item.get("role") in ("user", "assistant")
        and isinstance(item.get("content"), str)
    )
    messages.append({"role": "user", "content": message})

    generic_reply = GENERIC_REPLIES.get(message.casefold().rstrip("!?.,"))
    if generic_reply:
        CHAT_HISTORY[chat_id] = (
            history
            + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": generic_reply},
            ]
        )[-MAX_HISTORY_MESSAGES:]
        return jsonify(reply=generic_reply)

    if not GROQ_API_KEY:
        return jsonify(error="GROQ_API_KEY is not configured on the server."), 503

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "stream": False,
    }
    outbound = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "health-ai-project/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(outbound, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return jsonify(error=f"Groq returned an error ({exc.code}): {detail[:500]}"), 502
    except (URLError, TimeoutError) as exc:
        return jsonify(error=f"Could not connect to Groq: {exc}"), 503
    except ValueError as exc:
        return jsonify(error=f"Groq returned an invalid response: {exc}"), 502

    choices = result.get("choices") if isinstance(result, dict) else None
    first_choice = choices[0] if isinstance(choices, list) and choices else None
    assistant_data = (
        first_choice.get("message") if isinstance(first_choice, dict) else None
    )
    assistant_message = (
        assistant_data.get("content") if isinstance(assistant_data, dict) else None
    )
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        return jsonify(error="Groq returned an empty or invalid response."), 502

    CHAT_HISTORY[chat_id] = (
        messages[1:] + [{"role": "assistant", "content": assistant_message}]
    )[-MAX_HISTORY_MESSAGES:]
    return jsonify(reply=assistant_message)


@app.post("/api/clear")
def clear_chat():
    chat_id = session.get("chat_id")
    if chat_id:
        CHAT_HISTORY.pop(chat_id, None)
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
