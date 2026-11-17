"""Phase 4 - A small web server with a chat page for the bot.

Run:
    python server.py            # then open http://localhost:5000

Endpoints:
    GET  /           the chat page (static/chat.html)
    POST /api/chat   {"question": "..."} -> {"answer", "sources", "not_found"}
    GET  /api/health quick check that the index loaded
"""
import os

import anthropic
from flask import Flask, jsonify, request, send_from_directory

import config
from answer import answer, get_client
from index import SearchIndex

app = Flask(__name__, static_folder="static")

_index = SearchIndex()  # built once at start-up (takes a second or two)
_client = None


def client() -> anthropic.Anthropic:
    """Create the Claude client on first use, so the page still loads without a key."""
    global _client
    if _client is None:
        _client = get_client()
    return _client


def error(message: str, status: int):
    return jsonify({"error": message}), status


@app.get("/")
def chat_page():
    return send_from_directory(app.static_folder, "chat.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "chunks": len(_index.chunks), "company": config.COMPANY_NAME})


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = data.get("question")
    if not isinstance(question, str) or not question.strip():
        return error("Please type a question.", 400)
    question = question.strip()
    if len(question) > config.MAX_QUESTION_CHARS:
        return error(f"Please keep questions under {config.MAX_QUESTION_CHARS} characters.", 400)

    try:
        result = answer(question, _index, client())
    except SystemExit:  # get_client() found no API key
        return error("The chatbot isn't set up yet (no API key on the server).", 503)
    except anthropic.AuthenticationError:
        return error("The chatbot's API key was rejected.", 503)
    except anthropic.RateLimitError:
        return error("Lots of questions right now - please try again in a moment.", 429)
    except (anthropic.APIStatusError, anthropic.APIConnectionError):
        app.logger.exception("Claude API call failed")
        return error("Sorry, something went wrong. Please try again.", 502)

    return jsonify({k: result[k] for k in ("answer", "sources", "not_found")})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Chat page: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
