import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
from adiuvare import Guard

app = FastAPI(title="Adiuvare FastAPI Demo")

guard = Guard.from_config("adiuvare.yaml")
guard.use(app, framework="fastapi")

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
        "/api/v1/advanced-policy/": {
            "policy": "custom_profile",
            "sensitivity": "critical",
            "trackB": True,
        }
    }
)

class ReviewPayload(BaseModel):
    message: str

class HardStopPayload(BaseModel):
    comment: str

class AdvancedPayload(BaseModel):
    data_stream: str
    client_entropy: float

@app.get("/")
async def root():
    return {"route": "health-check", "status": "online"}

@app.get("/public/")
async def public():
    return {"route": "public", "message": "This route is exempt from Adiuvare inspection."}

@app.get("/protected/")
async def protected(request: Request):
    event = getattr(request.state, "adiuvare_event", None)
    return {
        "route": "protected",
        "message": "This stricter route passed Adiuvare inspection.",
        "verdict": getattr(event, "verdict", None) if event else "allow",
        "score": getattr(event, "score", None) if event else 0.0,
    }

@app.post("/review/")
async def review(payload: ReviewPayload, request: Request):
    event = getattr(request.state, "adiuvare_event", None)
    return {
        "route": "review",
        "message": "Payload review route reached the FastAPI view.",
        "received": {"message": payload.message},
        "verdict": getattr(event, "verdict", None) if event else "allow",
    }

@app.post("/hard-stop/")
async def hard_stop(payload: HardStopPayload, request: Request):
    event = getattr(request.state, "adiuvare_event", None)
    return {
        "route": "hard-stop",
        "message": "If Adiuvare allows the request, this fallback response is returned.",
        "received": {"comment": payload.comment},
        "verdict": getattr(event, "verdict", None) if event else "flag",
        "score": getattr(event, "score", None) if event else 0.45,
    }

# CASE A: Per-Endpoint Explicit Exemption Override
@app.get("/api/v1/explicit-exempt/")
@guard.exempt()  # Explicit inline code decorator overriding configuration matrix blocks
async def explicit_override_endpoint():
    """
    Demonstrates per-endpoint control. This inline decorator pattern explicitly forces an
    exemption bypass, taking structural precedence over systemic routing matrices.
    """
    return {"route": "explicit-exempt", "message": "Bypassed via direct per-endpoint decorator."}

# CASE B: Self-Described Custom Signal Processing Block
@app.post("/api/v1/advanced-policy/")
async def self_described_signal_route(payload: AdvancedPayload, request: Request):
    """
    Demonstrates a self-described signal edge case. Analyzes payload parameters directly
    within the application execution frame, recalculates dynamic risk, and injects runtime
    telemetry mutations back into the active Adiuvare event tracking wrapper before processing.
    """
    event = getattr(request.state, "adiuvare_event", None)
    
    # Custom business-logic validation heuristic simulation
    calculated_risk = 0.02
    if "override" in payload.data_stream.lower():
        calculated_risk += 0.55
    if payload.client_entropy > 0.90:
        calculated_risk += 0.25

    # Dynamically updating and elevating the Adiuvare context based on the self-described loop
    if event and calculated_risk > 0.50:
        event.verdict = "flag" if event.verdict == "allow" else event.verdict
        event.score = max(getattr(event, "score", 0.0), calculated_risk)

    return {
        "route": "advanced-payload-review",
        "self_described_internal_risk": calculated_risk,
        "final_adiuvare_verdict": getattr(event, "verdict", "allow") if event else "allow",
        "final_adiuvare_score": getattr(event, "score", calculated_risk) if event else calculated_risk
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)