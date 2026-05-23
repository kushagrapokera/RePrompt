import re


def strip_extra_whitespace(text: str) -> str:
    """Collapse multiple spaces, tabs, and newlines into single spaces."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text)
    return text.strip()


def fix_repeated_punctuation(text: str) -> str:
    """Collapse repeated punctuation (!!!, ???, ,,, etc.) to single."""
    text = re.sub(r"\.{3,}", "…", text)
    text = re.sub(r"[!]{2,}", "!", text)
    text = re.sub(r"[?]{2,}", "?", text)
    text = re.sub(r"[,]{2,}", ",", text)
    return text


def fix_casing_noise(text: str) -> str:
    """Fix ALL CAPS (unless it's a short word like I or OK)."""
    words = text.split()
    fixed = []
    for w in words:
        if w.isupper() and len(w) > 3:
            fixed.append(w.capitalize())
        else:
            fixed.append(w)
    return " ".join(fixed)


def remove_leading_trailing_noise(text: str) -> str:
    """Strip leading/trailing non-alphanumeric junk."""
    text = re.sub(r"^[\W_]+", "", text)
    text = re.sub(r"[\W_]+$", "", text)
    return text


def normalize_apostrophes(text: str) -> str:
    """Replace fancy quotes/apostrophes with ASCII equivalents."""
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "--")
    return text


def cleanup(text: str) -> str:
    """Run all cleanup steps on a raw query string."""
    if not text or not text.strip():
        return text

    text = normalize_apostrophes(text)
    text = strip_extra_whitespace(text)
    text = fix_repeated_punctuation(text)
    text = fix_casing_noise(text)
    text = remove_leading_trailing_noise(text)
    return text
