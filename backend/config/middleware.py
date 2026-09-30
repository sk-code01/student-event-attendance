"""
Request hygiene that belongs in front of every view.

`RejectNullBytesMiddleware` — PostgreSQL text columns cannot hold a NUL
byte, so a `%00` smuggled into any query-string filter that reaches a text
lookup (`?search=`, `?category=`, `?action=` ...) surfaces as `DataError` and
a 500. DRF's `CharField` already refuses NUL in request bodies; this closes
the same hole for the query string and the path, answering 400 before any
view runs. Found by the Phase 9 input-hardening suite.
"""

from urllib.parse import unquote

from django.http import JsonResponse


class RejectNullBytesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # request.path is already percent-decoded once by Django; the query
        # string is raw, so decode it once here. Never decode twice, or a
        # legitimate literal '%00' in a value would be misread as NUL.
        if '\x00' in request.path or '\x00' in unquote(request.META.get('QUERY_STRING', '')):
            return JsonResponse({'detail': 'Null bytes are not permitted in the request URL.'}, status=400)
        return self.get_response(request)
