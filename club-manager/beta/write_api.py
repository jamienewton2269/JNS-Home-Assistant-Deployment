"""Authenticated write adapter; no direct table access."""
from contextlib import closing
from http.cookies import SimpleCookie
from officer_controller import COOKIE_NAME

ACTIONS = frozenset(("join", "party", "attendance", "decision", "policy"))

def write_seniority(connect, cookie_header, body):
    if not isinstance(cookie_header, str) or len(cookie_header) > 4096:
        raise PermissionError("Invalid session")
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    item = cookie.get(COOKIE_NAME)
    if item is None or not 40 <= len(item.value) <= 256:
        raise PermissionError("Named officer session required")
    if not isinstance(body, dict) or set(body) != {"action", "data"}:
        raise ValueError("Invalid request")
    action, data = body["action"], body["data"]
    if not isinstance(action, str) or action not in ACTIONS or not isinstance(data, dict):
        raise ValueError("Invalid operation")
    import json
    with closing(connect()) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT club.api_seniority_write(%s,%s,%s::jsonb)",
                            (item.value, action, json.dumps(data)))
                result = cur.fetchone()[0]
    return result
