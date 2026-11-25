"""Authenticated write adapter; no direct table access."""
from contextlib import closing
from http.cookies import SimpleCookie
from officer_controller import COOKIE_NAME

ACTIONS = frozenset(("join", "party", "attendance", "decision", "policy", "membership_request", "membership_review"))

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
                if action == "membership_request":
                    cur.execute("SELECT club.api_membership_request(%s,%s::jsonb)", (item.value,json.dumps(data)))
                elif action == "membership_review":
                    if set(data) != {"request_id","approve","note"} or type(data["approve"]) is not bool or not isinstance(data["note"],str):
                        raise ValueError("Invalid review")
                    cur.execute("SELECT club.api_membership_review(%s,%s::uuid,%s,%s)", (item.value,data["request_id"],data["approve"],data["note"]))
                else:
                    cur.execute("SELECT club.api_seniority_write(%s,%s,%s::jsonb)", (item.value,action,json.dumps(data)))
                result = cur.fetchone()[0]
    return result
