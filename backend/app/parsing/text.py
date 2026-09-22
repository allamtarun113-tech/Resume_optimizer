import hashlib
import re
import unicodedata

# Characters PDFs commonly use for bullets; normalized to "-" so prompts and hashes are stable.
_BULLETS = "•●○◦▪▫■□►▸‣⁃∙·"
_BULLET_RE = re.compile(rf"^[ \t]*[{_BULLETS}][ \t]*", re.MULTILINE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES_RE = re.compile(r"[ \t  -​  　]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Canonical form of extracted text, used for prompts and cache keys."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    text = _BULLET_RE.sub("- ", text)
    text = _SPACES_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def text_hash(text: str) -> str:
    """sha256 of already-normalized text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
