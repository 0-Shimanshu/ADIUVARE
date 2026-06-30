from pathlib import Path

from flask import Flask, jsonify, request

from adiuvare import Guard

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)

guard = Guard.from_config(BASE_DIR / "adiuvare.yaml")

# ── Route table for routes that don't need decorator-level overrides ─────────
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


# ── 1. Health check — exempt ─────────────────────────────────────────────────
@app.get("/")
def health():
    return jsonify({"ok": True, "message": "Flask demo is running."})


# ── 2. Public route — exempt ─────────────────────────────────────────────────
@app.get("/public/")
def public():
    return jsonify(
        {
            "route": "public",
            "message": "This route is exempt from Adiuvare inspection.",
        }
    )


# ── 3. Protected route — admin policy via configure_routes ───────────────────
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


# ── 4. Payload review route — search policy via configure_routes ─────────────
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


# ── 5. Hard-stop route — critical sensitivity via configure_routes ────────────
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


# ── 6. Auth login — @guard.policy() decorator ────────────────────────────────
@app.post("/auth/login/")
@guard.policy("auth")
def auth_login():
    """
    Shows @guard.policy() used directly on a route instead of configure_routes.
    The auth policy raises sensitivity on login endpoints so rapid retries or
    injection attempts in the body score higher and escalate faster.
    """
    body = request.get_json(silent=True) or {}
    event = request.environ.get("adiuvare.event")

    return jsonify(
        {
            "route": "auth-login",
            "user": body.get("username", ""),
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )


# ── 7. Admin action — @guard.protect() decorator ─────────────────────────────
@app.post("/admin/action/")
@guard.protect(sensitivity="critical", ai_mode="assist", sink_mode="inline")
def admin_action():
    """
    Shows @guard.protect() used directly on a route with all posture fields
    spelled out explicitly. Requests above the block threshold are stopped
    before this handler runs; requests in the flag/throttle band are held
    for inline AI review before a verdict is issued.
    """
    body = request.get_json(silent=True) or {}
    event = request.environ.get("adiuvare.event")

    return jsonify(
        {
            "route": "admin-action",
            "action": body.get("action", ""),
            "accepted": True,
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )


# ── Runtime hook — print every verdict to stdout ─────────────────────────────
@guard.hooks.on_event
def log_event(event):
    print(
        f"[adiuvare] {event.verdict:<9} "
        f"identity={event.identity}  "
        f"endpoint={event.endpoint}"
    )


if __name__ == "__main__":
    # threaded=True is recommended for the WSGI path so concurrent requests
    # each get their own thread; Flask's dev server defaults to single-threaded.
    app.run(host="127.0.0.1", port=5000, threaded=True)
