"""Deterministic speech normalization, with no additional model call."""
import re
import unicodedata

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()


def number(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return number(n // 100) + " hundred" + (" " + number(n % 100) if n % 100 else "")
    if 1000 <= n < 2000 and n % 100 == 0:
        return number(n // 100) + " hundred"
    for size, name in [(10000000, "crore"), (100000, "lakh"), (1000, "thousand")]:
        if n >= size:
            return number(n // size) + " " + name + (" " + number(n % size) if n % size else "")


def language_for(text, default="en-IN"):
    for start, end, lang in [(0x0900,0x097f,"hi-IN"), (0x0b80,0x0bff,"ta-IN"),
                              (0x0c00,0x0c7f,"te-IN"), (0x0c80,0x0cff,"kn-IN"),
                              (0x0980,0x09ff,"bn-IN"), (0x0a80,0x0aff,"gu-IN"),
                              (0x0d00,0x0d7f,"ml-IN"), (0x0a00,0x0a7f,"pa-IN"),
                              (0x0b00,0x0b7f,"od-IN")]:
        if any(start <= ord(c) <= end for c in text):
            return "mr-IN" if lang == "hi-IN" and default == "mr-IN" else lang
    if re.search(r"\b(hai|hain|aap|kya|chahiye|namaste|ji|karna)\b", text, re.I):
        return "hi-IN"
    return "en-IN" if re.search(r"[a-zA-Z]", text) else default


def speakable(text):
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^[\s]*[#>*-]+\s*|^\s*\d+\.\s+", "", text, flags=re.M)
    text = re.sub(r"[|*_`~]", " ", text)
    text = "".join(c for c in text if unicodedata.category(c) != "So" and c not in "\ufe0f\u200d")
    text = re.sub(r"(?:Rs\.?|INR|₹)\s*([\d,]+)(?:\.(\d{1,2}))?",
                  lambda m: number(int(m[1].replace(",", ""))) + " rupees" +
                  (" and " + number(int(m[2].ljust(2, '0'))) + " paise" if m[2] else ""), text)
    def clock(m):
        h, minute = int(m[1]), int(m[2])
        if h > 23 or minute > 59:
            return m[0]
        suffix = (m[3] or ("AM" if h < 12 else "PM")).upper()
        return number(h % 12 or 12) + (" " + ("oh " if minute < 10 else "") + number(minute) if minute else "") + " " + suffix
    text = re.sub(r"\b(\d{1,2}):(\d{2})(?:\s*(AM|PM))?\b", clock, text, flags=re.I)
    for short, full in [(r"\bmins?\b", "minutes"), (r"\bhrs?\b", "hours"), (r"\bappt\b", "appointment")]:
        text = re.sub(short, full, text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


class SentenceChunker:
    def __init__(self, limit=220):
        self.buffer = ""
        self.limit = limit

    def feed(self, text, final=False):
        self.buffer += text
        chunks = []
        while self.buffer:
            boundary = next((m for m in re.finditer(r"[.!?।](?:\s|$)", self.buffer)
                if not re.search(r"\b(?:Rs|Dr|Mr|Mrs|Ms)\.$", self.buffer[:m.start()+1], re.I)), None)
            end = boundary.end() if boundary else 0
            if not end and len(self.buffer) >= self.limit:
                end = self.buffer.rfind(" ", 0, self.limit) or self.limit
            if not end and final:
                end = len(self.buffer)
            if not end:
                break
            chunk, self.buffer = self.buffer[:end].strip(), self.buffer[end:].lstrip()
            if chunk:
                chunks.append(chunk)
        return chunks
