import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import requests

API_URL = "http://10.3.2.112:11434/api/chat"
MODEL = "qwen2.5:32b-coder"


def _server_reachable():
    try:
        requests.get(API_URL.replace("/api/chat", "/api/tags"), timeout=3)
        return True
    except requests.exceptions.RequestException:
        return False


requires_lab_server = pytest.mark.skipif(
    not _server_reachable(),
    reason="lab Ollama server (10.3.2.112:11434) is not reachable from this machine",
)
