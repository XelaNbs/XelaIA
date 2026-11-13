"""Text normalization for the optional mail adapter. Job logic lives in agents/emploi.py."""
import html
import re

def plain(value):
    value=html.unescape(html.unescape(value or ""))
    value=re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.I|re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()
