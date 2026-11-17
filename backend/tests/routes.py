"""The app's API routes, flattened for tests that check every route."""

from fastapi.routing import APIRoute, iter_route_contexts


def api_routes(app):
    """Every API route with its full path. Since FastAPI 0.163, `app.routes` holds one entry
    per included router, so a loop over it alone sees only `/` and `/health` and passes
    without checking anything (R5)."""
    return [r for r in iter_route_contexts(app.routes) if isinstance(r.original_route, APIRoute)]
