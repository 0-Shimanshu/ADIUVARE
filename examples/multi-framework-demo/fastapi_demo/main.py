from fastapi import FastAPI, Request
from pydantic import BaseModel
from adiuvare import Guard
import os

app = FastAPI(title="Adiuvare FastAPI Demo")

config_path = os.path.join(os.path.dirname(__file__), "adiuvare.yaml")
guard = Guard.from_config(config_path)
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
        },
        "/api/v1/global-policy-override/": {
            "policy": "search",
            "sensitivity": "public",
            "trackB": False,
        },
        "/api/v1/global-protect-override/": {
            "sensitivity": "internal",
            "trackB": False,
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
    Demonstrates per-endpoint control. This inline decorator explicitly exempts
    the route from Adiuvare inspection, overriding global configuration.
    """
    return {"route": "explicit-exempt", "message": "Bypassed via direct per-endpoint decorator."}

# CASE B: Self-Described Custom Signal Processing Block
@app.post("/api/v1/advanced-policy/")
async def self_described_signal_route(payload: AdvancedPayload, request: Request):
    """
    Demonstrates dynamically updating Adiuvare context based on application logic.
    Analyzes the payload, calculates custom risk, and updates the active event.
    """
    event = getattr(request.state, "adiuvare_event", None)
    
    # Custom application-level risk calculation
    calculated_risk = 0.02
    if "override" in payload.data_stream.lower():
        calculated_risk += 0.55
    if payload.client_entropy > 0.90:
        calculated_risk += 0.25

    # Update the Adiuvare event with our calculated risk
    if event and calculated_risk > 0.50:
        event.verdict = "flag" if event.verdict == "allow" else event.verdict
        event.score = max(getattr(event, "score", 0.0), calculated_risk)

    return {
        "route": "advanced-payload-review",
        "self_described_internal_risk": calculated_risk,
        "final_adiuvare_verdict": getattr(event, "verdict", "allow") if event else "allow",
        "final_adiuvare_score": getattr(event, "score", calculated_risk) if event else calculated_risk
    }

# CASE C: Endpoint Overriding Global Policy with @guard.policy
@app.get("/api/v1/global-policy-override/")
@guard.policy("admin", sensitivity="critical", trackB=True)
async def global_policy_override_route(request: Request):
    """
    Demonstrates overriding a global configuration with a decorator-based policy.
    The global config sets policy to 'search' (public, no trackB), but this decorator
    elevates it to 'admin' (critical, trackB=True).
    """
    event = getattr(request.state, "adiuvare_event", None)
    return {
        "route": "global-policy-override",
        "message": "Overrode global policy using @guard.policy decorator.",
        "verdict": getattr(event, "verdict", None) if event else "allow",
        "score": getattr(event, "score", None) if event else 0.0,
    }

# CASE D: Endpoint Overriding Global Config with @guard.protect
@app.get("/api/v1/global-protect-override/")
@guard.protect(sensitivity="critical", trackB=True)
async def global_protect_override_route(request: Request):
    """
    Demonstrates overriding a global configuration with a decorator-based protect rule.
    The global config sets sensitivity to 'internal' and trackB to False, but this decorator
    elevates it to sensitivity 'critical' and trackB to True.
    """
    event = getattr(request.state, "adiuvare_event", None)
    return {
        "route": "global-protect-override",
        "message": "Overrode global protect rule using @guard.protect decorator.",
        "verdict": getattr(event, "verdict", None) if event else "allow",
        "score": getattr(event, "score", None) if event else 0.0,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)