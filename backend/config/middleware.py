from django.http import JsonResponse


class HealthCheckMiddleware:
    """Short-circuit /health/ before ALLOWED_HOSTS validation runs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return JsonResponse({"status": "ok"})
        return self.get_response(request)
