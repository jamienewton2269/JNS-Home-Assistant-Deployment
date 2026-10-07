"""JNS Network Identity: deterministic MAC-derived DNS identities."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from aiohttp import BasicAuth
import voluptuous as vol

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA, MODE_STORAGE
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

DOMAIN = "jns_network_identity"
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)
SERVICE_IMPORT = "import_bindings"
STATUS_ENTITY = "sensor.jns_network_identity_status"
DNS_A = "10.10.10.247"
CARD_URL = "/jns-network-identity/card.js"
CARD_TYPE = "custom:jns-network-bindings-card"
IOT_FIRST = 150
IOT_LAST = 187
MAX_FILE = 2 * 1024 * 1024

MAC_RE = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])")
IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")


def _status(hass: HomeAssistant, state: str, **attrs: Any) -> None:
    old = hass.states.get(STATUS_ENTITY)
    merged = dict(old.attributes) if old else {}
    merged.update(attrs)
    merged["friendly_name"] = "JNS Network Identity Status"
    hass.states.async_set(STATUS_ENTITY, state, merged)


def _read_uploaded(hass: HomeAssistant, file_id: str) -> str:
    with process_uploaded_file(hass, file_id) as path:
        p = Path(path)
        if p.stat().st_size > MAX_FILE:
            raise HomeAssistantError("Binding file exceeds 2 MB safety limit")
        return p.read_text(encoding="utf-8-sig", errors="replace")


def _parse_bindings(text: str) -> tuple[dict[str, str], int]:
    """Return {fqdn: ip} for managed IoT bindings plus ignored-line count."""
    records: dict[str, str] = {}
    ip_to_name: dict[str, str] = {}
    ignored = 0

    for line in text.splitlines():
        ips = IP_RE.findall(line)
        macs = MAC_RE.findall(line)
        selected_ip = None
        for ip in ips:
            parts = ip.split(".")
            try:
                octets = [int(x) for x in parts]
            except ValueError:
                continue
            if any(x < 0 or x > 255 for x in octets):
                continue
            if octets[:3] == [10, 10, 10] and IOT_FIRST <= octets[3] <= IOT_LAST:
                selected_ip = ip
                break

        if selected_ip is None:
            continue
        if not macs:
            ignored += 1
            continue

        mac_hex = re.sub(r"[^0-9A-Fa-f]", "", macs[0]).upper()
        if len(mac_hex) != 12:
            ignored += 1
            continue

        name = f"JNS-{mac_hex[-6:]}.home.arpa"
        previous = records.get(name)
        if previous is not None and previous != selected_ip:
            raise HomeAssistantError(
                f"Conflicting binding for {name}: {previous} and {selected_ip}"
            )
        previous_name = ip_to_name.get(selected_ip)
        if previous_name is not None and previous_name != name:
            raise HomeAssistantError(
                f"IP {selected_ip} is bound to both {previous_name} and {name}"
            )

        records[name] = selected_ip
        ip_to_name[selected_ip] = name

    if not records:
        raise HomeAssistantError(
            "No valid DHCP/MAC bindings were found in 10.10.10.150-187"
        )
    return records, ignored


async def _admin_required(hass: HomeAssistant, call: ServiceCall) -> None:
    if call.context.user_id is None:
        return
    user = await hass.auth.async_get_user(call.context.user_id)
    if user is None or not user.is_admin:
        raise HomeAssistantError("Administrator permission is required")


def _dns_a_entry(hass: HomeAssistant):
    entries = hass.config_entries.async_entries("adguard")
    for entry in entries:
        if str(entry.data.get(CONF_HOST, "")).strip() == DNS_A:
            return entry
    raise HomeAssistantError(
        "AdGuard Home integration for DNS-A (10.10.10.247) is not configured on HA-General"
    )


async def _adguard_json(
    hass: HomeAssistant,
    entry,
    method: str,
    endpoint: str,
    payload: dict[str, str] | None = None,
):
    scheme = "https" if entry.data.get(CONF_SSL) else "http"
    port = int(entry.data.get(CONF_PORT, 3000))
    url = f"{scheme}://{DNS_A}:{port}/control/{endpoint}"
    session = async_get_clientsession(hass, bool(entry.data.get(CONF_VERIFY_SSL, True)))
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    auth = BasicAuth(username, password or "") if username else None

    async with session.request(
        method,
        url,
        auth=auth,
        json=payload,
        timeout=20,
        ssl=None if entry.data.get(CONF_VERIFY_SSL, True) else False,
    ) as response:
        if response.status >= 400:
            body = await response.text()
            raise HomeAssistantError(
                f"DNS-A AdGuard API {endpoint} failed: HTTP {response.status}: {body[:200]}"
            )
        if response.content_type == "application/json":
            return await response.json()
        text = await response.text()
        return text


async def _apply_records(
    hass: HomeAssistant, records: dict[str, str]
) -> tuple[int, int]:
    entry = _dns_a_entry(hass)
    current = await _adguard_json(hass, entry, "GET", "rewrite/list")
    if not isinstance(current, list):
        raise HomeAssistantError("Unexpected DNS-A rewrite list response")

    by_domain: dict[str, list[str]] = {}
    for item in current:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain", ""))
        answer = str(item.get("answer", ""))
        by_domain.setdefault(domain.lower(), []).append(answer)

    changed = 0
    unchanged = 0

    for domain, ip in sorted(records.items()):
        key = domain.lower()
        existing = by_domain.get(key, [])
        if ip in existing and len(existing) == 1:
            unchanged += 1
            continue

        # Only delete rewrites for the exact deterministic name being imported.
        for old_answer in existing:
            await _adguard_json(
                hass,
                entry,
                "POST",
                "rewrite/delete",
                {"domain": domain, "answer": old_answer},
            )

        await _adguard_json(
            hass,
            entry,
            "POST",
            "rewrite/add",
            {"domain": domain, "answer": ip},
        )
        changed += 1

    # Verify master contains every imported mapping.
    verify = await _adguard_json(hass, entry, "GET", "rewrite/list")
    seen = {
        (str(x.get("domain", "")).lower(), str(x.get("answer", "")))
        for x in verify
        if isinstance(x, dict)
    }
    missing = [
        f"{domain}->{ip}"
        for domain, ip in records.items()
        if (domain.lower(), ip) not in seen
    ]
    if missing:
        raise HomeAssistantError(
            "DNS-A verification failed for: " + ", ".join(missing[:8])
        )

    return changed, unchanged


async def _ensure_card_resource(hass: HomeAssistant) -> str:
    """Register the card as a Lovelace resource without creating a dashboard."""
    data = hass.data.get(LOVELACE_DATA)
    if data is None:
        return "lovelace-unavailable"
    if data.resource_mode != MODE_STORAGE:
        return "yaml-resource-mode"

    resources = data.resources
    await resources.async_get_info()
    items = resources.async_items() or []
    if any(str(item.get("url", "")).split("?")[0] == CARD_URL for item in items):
        return "present"

    await resources.async_create_item({"res_type": "module", "url": CARD_URL})
    return "created"


async def _ensure_network_subview(hass: HomeAssistant) -> str:
    """Add Network Infrastructure as a subview under an existing Config view."""
    data = hass.data.get(LOVELACE_DATA)
    if data is None:
        return "lovelace-unavailable"

    for dashboard_path, dashboard in data.dashboards.items():
        try:
            conf = await dashboard.async_load(False)
        except Exception:
            continue
        if not isinstance(conf, dict) or not isinstance(conf.get("views"), list):
            continue

        views = conf["views"]
        config_view = next(
            (
                view
                for view in views
                if isinstance(view, dict)
                and (
                    str(view.get("title", "")).strip().lower() == "config"
                    or str(view.get("path", "")).strip().lower() == "config"
                )
            ),
            None,
        )
        if config_view is None:
            continue

        if any(
            isinstance(view, dict)
            and str(view.get("path", "")).strip().lower() == "network-infrastructure"
            for view in views
        ):
            return "present"

        base = "lovelace" if dashboard_path is None else str(dashboard_path)
        navigation_path = f"/{base}/network-infrastructure"

        cards = config_view.setdefault("cards", [])
        if isinstance(cards, list) and not any(
            isinstance(card, dict)
            and card.get("navigation_path") == navigation_path
            for card in cards
        ):
            cards.append(
                {
                    "type": "button",
                    "name": "Network Infrastructure",
                    "icon": "mdi:lan",
                    "show_state": False,
                    "tap_action": {
                        "action": "navigate",
                        "navigation_path": navigation_path,
                    },
                }
            )

        views.append(
            {
                "title": "Network Infrastructure",
                "path": "network-infrastructure",
                "subview": True,
                "icon": "mdi:lan",
                "cards": [{"type": CARD_TYPE}],
            }
        )

        try:
            await dashboard.async_save(conf)
        except Exception:
            return "save-failed"
        return "created"

    return "config-view-not-found"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up JNS Network Identity."""
    card_path = str(Path(__file__).parent / "card.js")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, card_path, cache_headers=False)]
    )

    _status(
        hass,
        "ready",
        last_run="Never",
        parsed=0,
        changed=0,
        unchanged=0,
        ignored=0,
        scope="10.10.10.150-187",
        naming="JNS-<last-6-MAC>.home.arpa",
        dns_master=DNS_A,
    )

    async def import_bindings(call: ServiceCall) -> None:
        await _admin_required(hass, call)
        file_id = str(call.data["file_id"])
        _status(hass, "working")
        try:
            text = await hass.async_add_executor_job(_read_uploaded, hass, file_id)
            records, ignored = _parse_bindings(text)
            changed, unchanged = await _apply_records(hass, records)
        except Exception as err:
            _status(
                hass,
                "error",
                last_run=datetime.now().astimezone().isoformat(timespec="seconds"),
                error=str(err),
            )
            raise

        _status(
            hass,
            "ok",
            last_run=datetime.now().astimezone().isoformat(timespec="seconds"),
            parsed=len(records),
            changed=changed,
            unchanged=unchanged,
            ignored=ignored,
            error="",
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT,
        import_bindings,
        schema=vol.Schema({vol.Required("file_id"): str}),
    )

    async def finish_frontend_setup(_event=None) -> None:
        resource = await _ensure_card_resource(hass)
        subview = await _ensure_network_subview(hass)
        _status(hass, hass.states[STATUS_ENTITY].state, resource=resource, subview=subview)

    @callback
    def started(_event) -> None:
        hass.async_create_task(finish_frontend_setup())

    if hass.is_running:
        hass.async_create_task(finish_frontend_setup())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, started)

    return True
