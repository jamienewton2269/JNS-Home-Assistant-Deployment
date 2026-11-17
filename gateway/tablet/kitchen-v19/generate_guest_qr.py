#!/usr/bin/env python3
"""Build-time static guest-portal QR (no credentials, safe for staging).

Dependency on development PC: pip install qrcode[pil]
Do NOT run on Android/tablet. Output PNG is copied into the Android project
as res/drawable-nodpi/jns_guest_portal_qr.png.
"""
import argparse
from pathlib import Path
from urllib.parse import urlsplit

def safe_url(raw):
    parsed = urlsplit(raw)
    if (parsed.scheme != "https" or parsed.hostname != "ha-general.home.arpa"
            or parsed.port != 8449 or parsed.path not in ("", "/")
            or parsed.username or parsed.password or parsed.query
            or parsed.fragment):
        raise ValueError("Only the credential-free LAN guest portal HTTPS URL is allowed")
    return "https://ha-general.home.arpa:8449/"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://ha-general.home.arpa:8449/")
    parser.add_argument("--out", default="res/drawable-nodpi/jns_guest_portal_qr.png")
    args = parser.parse_args()
    url = safe_url(args.url)
    import qrcode
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    qr.make_image(fill_color="black", back_color="white").save(output)
    print("TEST-ONLY QR created at", output)
    print("Encodes credential-free LAN guest portal:", url)
    print("NOTICE: portal currently serves a ha.jnsystems.xyz certificate;")
    print("the LAN hostname certificate mismatch must be fixed before normal use.")

if __name__ == "__main__":
    main()
