import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

def ssl_context():
    # python.org installs on macOS can lack a configured CA bundle.
    for path in (os.environ.get("SSL_CERT_FILE"), "/opt/homebrew/etc/ca-certificates/cert.pem", "/etc/ssl/cert.pem"):
        if path and os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()

def request(url, data=None, headers=None, timeout=30, limit=12000000):
    encoded = json.dumps(data).encode() if data is not None else None
    h = {"User-Agent": "JarvisLocal/0.1 (personal job research)", **(headers or {})}
    if encoded:
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=encoded, headers=h)
    with urllib.request.urlopen(req, context=ssl_context(), timeout=timeout) as response:
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError("Réponse trop volumineuse")
        return body

def api(url, data=None, headers=None, timeout=30):
    return json.loads(request(url, data, headers, timeout))
