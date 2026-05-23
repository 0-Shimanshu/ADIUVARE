import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


def health(request):
    return JsonResponse(
        {
            "ok": True,
            "message": "Django demo is running.",
        }
    )


def public(request):
    return JsonResponse(
        {
            "route": "public",
            "message": "This route is exempt from Adiuvare inspection.",
        }
    )


def protected(request):
    event = getattr(request, "adiuvare_event", None)

    return JsonResponse(
        {
            "route": "protected",
            "message": "This stricter route passed Adiuvare inspection.",
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )


@csrf_exempt
def review(request):
    payload = _read_json(request)
    event = getattr(request, "adiuvare_event", None)

    return JsonResponse(
        {
            "route": "review",
            "message": "Payload review route reached the Django view.",
            "received": payload,
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )


@csrf_exempt
def hard_stop(request):
    payload = _read_json(request)
    event = getattr(request, "adiuvare_event", None)

    return JsonResponse(
        {
            "route": "hard-stop",
            "message": "If Adiuvare allows the request, this fallback response is returned.",
            "received": payload,
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )


def _read_json(request):
    if not request.body:
        return {}

    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {"raw": request.body.decode("utf-8", errors="replace")}
