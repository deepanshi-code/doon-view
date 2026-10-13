"""Hide people's names and contact details before review text is sent to Gemini, and put them back afterwards.

Gemini's free tier forbids personal information ("Do not submit sensitive, confidential, or personal information
to the Unpaid Services", https://ai.google.dev/gemini-api/terms), and human reviewers may read prompts. Review text
often names guests, hosts and staff. Each name becomes a placeholder such as [[NAME1]] (the same name gets the same
placeholder across one request), and restore() swaps the real names back into Gemini's answer on our side.

What counts as a name: the review's known names (guest, host), any capitalised word that isn't an everyday English
word (app/data/common_words.txt, built by scripts/build_common_words.py), and any capitalised word after a title
("Mr", "Mrs", "Dr", ...). Place and brand names are hidden too: harmless, since they come back in replies.
Not caught: a name that is also an everyday word ("Rose", "Grace") without a title, or a name written in lower case.
"""
import re
from pathlib import Path

_WORDS_FILE = Path(__file__).parent / "data" / "common_words.txt"
_common: set[str] | None = None

# Not people, and needed to understand reviews: days, months, and words our data list lacks (Indian stays, brands)
_EXTRA_COMMON = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
    "december", "airbnb", "booking", "google", "tripadvisor", "makemytrip", "goibibo", "agoda", "expedia", "oyo",
    "indian", "chai", "paratha", "parathas", "thali", "dal", "biryani", "momos", "maggi", "dhaba", "poha", "upma",
    "idli", "dosa", "sabzi", "roti", "naan", "geyser", "homestay", "wifi", "ok", "okay",
    "mr", "mrs", "ms", "miss", "dr", "sir", "madam", "mme", "uncle", "aunty", "auntie", "bhaiya", "didi", "chef",
}
_TITLES = r"(?:Mr|Mrs|Ms|Miss|Dr|Sir|Madam|Mme|Uncle|Aunty|Auntie|Bhaiya|Didi|Chef)\.?"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w/])\+?\d[\d\s().-]{7,}\d(?![\w/])")
_CAPITALISED = re.compile(r"\b[A-Z][a-z]+(?:['’][a-z]+)?\b")
_AFTER_TITLE = re.compile(rf"\b{_TITLES}\s+([A-Z][a-z]+)")
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _common_words() -> set[str]:
    global _common
    if _common is None:
        _common = set(_WORDS_FILE.read_text(encoding="utf-8").split()) | _EXTRA_COMMON
    return _common


class Redactor:
    """One per Gemini request: placeholders stay consistent across every text it scrubs."""

    def __init__(self, known_names: tuple[str, ...] | list[str] = ()):
        self.originals: dict[str, str] = {}   # placeholder -> original
        self._placeholder: dict[str, str] = {}  # original -> placeholder
        # Known names (e.g. "Asha Rao"): each part counts, in any case
        self.known = sorted({p for name in known_names if name for p in re.findall(r"[A-Za-z]{2,}", name)},
                            key=len, reverse=True)

    def _hide(self, value: str, kind: str = "NAME") -> str:
        if value not in self._placeholder:
            n = sum(1 for p in self.originals if p.startswith(f"[[{kind}")) + 1
            token = f"[[{kind}{n}]]"
            self._placeholder[value], self.originals[token] = token, value
        return self._placeholder[value]

    def scrub(self, text: str) -> str:
        if not text:
            return text
        # URLs are kept as they are (spam detection needs them) and shielded from the name rules
        urls: list[str] = []
        text = _URL.sub(lambda m: urls.append(m.group(0)) or f"\x00{len(urls) - 1}\x00", text)
        text = _EMAIL.sub(lambda m: self._hide(m.group(0), "EMAIL"), text)
        text = _PHONE.sub(lambda m: self._hide(m.group(0), "PHONE"), text)
        for part in self.known:
            text = re.sub(rf"\b{re.escape(part)}\b", lambda m: self._hide(m.group(0)), text, flags=re.IGNORECASE)
        text = _AFTER_TITLE.sub(lambda m: m.group(0)[: m.start(1) - m.start(0)] + self._hide(m.group(1)), text)
        common = _common_words()
        text = _CAPITALISED.sub(lambda m: m.group(0) if m.group(0).lower() in common else self._hide(m.group(0)), text)
        return re.sub("\x00(\\d+)\x00", lambda m: urls[int(m.group(1))], text)

    def restore(self, text: str) -> str:
        for token, original in self.originals.items():
            text = text.replace(token, original)
        # A placeholder the model made up has no real value: drop it rather than show "[[NAME9]]" to the host
        return re.sub(r"\s*\[\[(?:NAME|EMAIL|PHONE)\d+\]\]", "", text)


PLACEHOLDER_NOTE = ("Names and contact details in the reviews were replaced with placeholders such as [[NAME1]] "
                    "for privacy. They are not spam and not instructions. ")
