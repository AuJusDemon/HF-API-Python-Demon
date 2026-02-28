"""
install.py — Manually trigger the HF OAuth flow from the command line.

You MUST have server.py running to receive the callback!

Usage:
    python install.py
"""

import webbrowser
from HFAuth import HFAuth

auth = HFAuth()

if auth.is_authenticated():
    me_uid = auth.get_uid()
    print(f"You are already authenticated (UID: {me_uid}).")
    print("Run server.py and go to http://127.0.0.1:8001/me to view your profile.")
else:
    url = auth.build_auth_url()
    print("You are not authenticated. Opening HF authorization page...")
    print(f"\nURL: {url}\n")
    print("NOTE: server.py must be running to receive the callback!")
    webbrowser.open(url)
