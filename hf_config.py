import os
HF_API_URL   = "https://hackforums.net/api/v2/"
CLIENT_ID    = os.environ.get("HF_CLIENT_ID", "")
SECRET_KEY   = os.environ.get("HF_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("HF_REDIRECT_URI", "")
STATE        = os.environ.get("HF_STATE", "")
