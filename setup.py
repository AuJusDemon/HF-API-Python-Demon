from setuptools import setup, find_packages

# Bug #13 note:
# 'requests' is still required because HFAuth.handle_token_exchange() and
# HFAuth.post_request() use the synchronous requests library for the OAuth
# token exchange. HFClient already has an async exchange_code_for_token()
# that uses httpx, but HFAuth hasn't been migrated to call it yet.
#
# To remove the requests dependency entirely:
#   1. Have HFAuth.handle_token_exchange() call asyncio.run(exchange_code_for_token(...))
#      from HFClient instead of doing its own requests.post().
#   2. Remove HFAuth.post_request() (only used internally).
#   3. Delete "requests" from install_requires below.

setup(
    name="hf-api",
    version="2.0.0",
    description="Full HackForums API v2 wrapper — async client, watcher, webhooks, CLI",
    author="AuJusDemon",
    url="https://github.com/AuJusDemon/HF-API-Python-Demon",
    py_modules=[
        # Config
        "cli", "hf_config",
        # Core
        "HFClient", "HFAuth",
        # Resource APIs
        "HFMe", "HFUsers", "HFPosts", "HFThreads", "HFForums",
        "HFBytes", "HFContracts", "HFBratings", "HFDisputes",
        "HFSigmarket",
        # Utilities
        "HFPaginator", "HFBBCode", "HFBBCodeBuilder",
        "HFWatcher", "HFWebhook",
        # New
        "HFBatch", "HFEventStore", "HFCache",
        "HFExceptions", "HFTypes",
    ],
    install_requires=[
        "httpx>=0.25.0",   # async HTTP client — all API calls
        "requests",        # sync OAuth token exchange in HFAuth (see note above)
        "flask",           # server.py web UI
        "click>=8.0",      # CLI
    ],
    entry_points={
        "console_scripts": [
            "hf=cli:cli",
        ],
    },
    python_requires=">=3.11",
)
