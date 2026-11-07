"""Club Manager read-only beta API adapter, for the existing CT101 Python app.

Never instantiate with the legacy clubmgr database connection. Inject a
dedicated authenticated connection factory whose PostgreSQL role has ONLY
the club_api_service read-projection grants. This module opens no port and
does not enable any HTTP route or session issuance.
"""
from contextlib import closing
import json

# Explicit routes are immutable. No user-controlled SQL identifier.
READ_ROUTES = {
    "/api/v1/dashboard": "SELECT club.api_dashboard_for_officer(%s)",
    "/api/v1/members": "SELECT club.api_members_for_officer(%s)",
    "/api/v1/moorings": "SELECT club.api_moorings_for_officer(%s)",
    "/api/v1/clubhouse": "SELECT club.api_clubhouse_for_officer(%s)",
    "/api/v1/renewals": "SELECT club.api_renewals_for_officer(%s)",
    "/api/v1/committee": "SELECT club.api_committee_for_officer(%s)",
    "/api/v1/security": "SELECT club.api_security_for_officer(%s)",
}

class ReadOnlyBetaAPI:
    def __init__(self, connection_factory):
        self.connect = connection_factory

    def get(self, path, opaque_session):
        """Return a JSON payload; PostgreSQL rechecks MFA and RBAC each time.

        Permission errors must map to HTTP 403, not 200 with an empty response.
        A reverse proxy/HTTP handler must set no-store, CSP and cookie policy.
        """
        statement = READ_ROUTES.get(path)
        if statement is None:
            raise LookupError("Unknown read route")
        if (not isinstance(opaque_session,str)
                or not 40 <= len(opaque_session) <= 256
                or any(ord(x) < 33 or ord(x) > 126 for x in opaque_session)):
            raise PermissionError("Authenticated officer session required")
        with closing(self.connect()) as cn:
            with cn:
                with cn.cursor() as cur:
                    cur.execute(statement, (opaque_session,))
                    row = cur.fetchone()
        if row is None or row[0] is None:
            raise RuntimeError("Read projection unavailable")
        data = row[0]
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, (dict, list)):
            raise RuntimeError("Unexpected read projection")
        return data
