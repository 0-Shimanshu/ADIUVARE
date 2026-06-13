from pathlib import Path

from flask import Flask, jsonify, request

from adiuvare import Guard

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)

guard = Guard.from_config(BASE_DIR / "adiuvare.yaml")

guard.configure_routes(
    {
        "/": {"exempt": True},
        "/public/": {"exempt": True},
        "/protected/": {
            "policy": "admin",
            "sensitivity": "critical",
            "trackB": True,
        },
        "/review/": {
            "policy": "search",
            "sensitivity": "internal",
            "trackB": True,
        },
        "/hard-stop/": {
            "sensitivity": "critical",
            "trackB": True,
        },
    }
)

guard.use(app, framework="flask")


@app.get("/")
def health():
    return jsonify(
        {
            "ok": True,
            "message": "Flask demo is running.",
        }
    )


@app.get("/public/")
def public():
    return jsonify(
        {
            "route": "public",
            "message": "This route is exempt from Adiuvare inspection.",
        }
    )


@app.get("/protected/")
def protected():
    event = request.environ.get("adiuvare.event")

    return jsonify(
        {
            "route": "protected",
            "message": "This stricter route passed Adiuvare inspection.",
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )


@app.post("/review/")
def review():
    payload = request.get_json(silent=True)

    if payload is None:
        payload = request.get_data(as_text=True)

    event = request.environ.get("adiuvare.event")

    return jsonify(
        {
            "route": "review",
            "message": "Payload review route reached the Flask view.",
            "received": payload,
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )


@app.post("/hard-stop/")
def hard_stop():
    payload = request.get_json(silent=True)

    if payload is None:
        payload = request.get_data(as_text=True)

    event = request.environ.get("adiuvare.event")

    return jsonify(
        {
            "route": "hard-stop",
            "message": "If Adiuvare allows the request, this fallback response is returned.",
            "received": payload,
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)