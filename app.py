import json
import os
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session


load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
SYSTEM_PROMPT = (
    "You are NEXORA AI, a helpful, clear, and friendly AI assistant. "
    "Your name is NEXORA AI. Answer the user's questions accurately and "
    "use Markdown formatting when it improves readability. If you are unsure "
    "or lack current information, be transparent instead of inventing facts."
)
GENERIC_REPLIES = {
    "hi": "Hi! How can I help you today?",
    "hello": "Hello! What can I help you with?",
    "hey": "Hey! How can I help?",
    "who are you": "I'm NEXORA AI, your friendly AI assistant.",
    "what is your name": "I'm NEXORA AI.",
    "who made you": "I was built to power this NEXORA AI chatbot.",
    "who created you": "I was built to power this NEXORA AI chatbot.",
}
MAX_MESSAGE_LENGTH = 10_000
MAX_HISTORY_MESSAGES = 40
CHAT_HISTORY = {}


@app.get("/")
def index():
    return render_template("index.html")


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
