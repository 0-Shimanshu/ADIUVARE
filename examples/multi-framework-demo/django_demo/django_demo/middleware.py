from pathlib import Path

from django.http import JsonResponse as DjangoJsonResponse

from adiuvare import Guard
from adiuvare.integrations.django import AdiuvareMiddleware

BASE_DIR = Path(__file__).resolve().parent.parent

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


def adiuvare_middleware(get_response):
    base_middleware = AdiuvareMiddleware(get_response, guard)

    def middleware(request):
        response = base_middleware(request)

        if hasattr(response, "data") and not hasattr(response, "content"):
            return DjangoJsonResponse(
                response.data,
                status=getattr(response, "status_code", 200),
            )

        return response

    return middleware
