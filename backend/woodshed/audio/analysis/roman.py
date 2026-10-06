"""Hindi in Devanagari -> Hindi in Roman letters, the way people text it.

"कैसे बताऊँ मैं तुम्हें" -> "kaise bataaun main tumhein"

Not a scholarly transliteration ("kaise batāūṁ"): casual spelling, with no
accents, because that is how lyrics are written and read online. It is rules,
not a model, so some spellings will differ from the ones you would pick - which
is why lyrics can be edited.

Anything that is not Devanagari (English words, digits, punctuation) passes
through untouched.

The one idea that makes it sound right: **schwa deletion**. Every Devanagari
consonant carries a built-in "a" (क is "ka"), but spoken Hindi drops it in
predictable places - at the end of a word (दिल is "dil", not "dila") and in the
middle where a consonant sits between two vowels (समझना is "samajhna", not
"samajhana"). Without this, every word comes out sounding like Sanskrit.
"""

import re
from dataclasses import dataclass

CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "ऩ": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ऱ": "r", "ल": "l", "ळ": "l", "ऴ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    # Precomposed nukta letters - sounds borrowed from Persian and Arabic.
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "d", "ढ़": "dh", "फ़": "f", "य़": "y",
}

# The nukta can also arrive as a separate dot after the letter.
NUKTA = "़"
WITH_NUKTA = {"k": "q", "j": "z", "ph": "f", "d": "d", "dh": "dh", "g": "gh", "kh": "kh"}

VOWELS = {  # standing on their own, e.g. at the start of a word
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ऍ": "e", "ऎ": "e", "ए": "e", "ऐ": "ai", "ऑ": "o", "ऒ": "o", "ओ": "o", "औ": "au",
}
SIGNS = {  # vowel marks attached to a consonant: का, कि, की...
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "ॅ": "e", "ॆ": "e", "े": "e", "ै": "ai", "ॉ": "o", "ॊ": "o", "ो": "o", "ौ": "au",
}
VIRAMA = "्"          # "no vowel here": joins consonants, as in प्यार
NASALS = {"ं", "ँ"}   # anusvara and chandrabindu: both read as a nasal n
VISARGA = "ः"
DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}
SILENT = {"।", "॥", "‌", "‍"}  # sentence marks, invisible joiners

LIPS = ("p", "ph", "b", "bh", "m")  # a nasal before these is an m: संभल -> sambhal

DEVANAGARI_RUN = re.compile(r"[ऀ-ॿ‌‍]+")


@dataclass
class Unit:
    """One sound-slot: a consonant with its vowel, or a vowel on its own."""
    consonant: str
    vowel: str          # "a" is the built-in vowel; "" means none
    nasal: bool = False
    visarga: bool = False


def romanise(text: str) -> str:
    """Convert every Devanagari word in `text`, leaving everything else alone."""
    return DEVANAGARI_RUN.sub(lambda match: _word(match.group()), text)


def _word(chars: str) -> str:
    units = _parse(chars)
    if not units:
        return "".join(DIGITS.get(c, "") for c in chars)
    _drop_schwas(units)
    return _spell(units)


def _parse(chars: str) -> list[Unit]:
    units: list[Unit] = []
    for c in chars:
        if c in CONSONANTS:
            units.append(Unit(CONSONANTS[c], "a"))
        elif c == NUKTA and units:
            units[-1].consonant = WITH_NUKTA.get(units[-1].consonant, units[-1].consonant)
        elif c in SIGNS and units:
            units[-1].vowel = SIGNS[c]
        elif c == VIRAMA and units:
            units[-1].vowel = ""
        elif c in VOWELS:
            units.append(Unit("", VOWELS[c]))
        elif c in NASALS:
            if units:
                units[-1].nasal = True
        elif c == VISARGA and units:
            units[-1].visarga = True
        elif c in DIGITS:
            units.append(Unit(DIGITS[c], ""))
        # anything else (sentence marks, joiners) is silent
    return units


def _drop_schwas(units: list[Unit]) -> None:
    """Remove the built-in "a" where spoken Hindi drops it."""
    sounded = [u for u in units if u.vowel]

    # At the end of a word: दिल -> dil. Kept in one-syllable words (न -> na)
    # and after clusters ending in r, y or v, which cannot be said without it
    # (मित्र -> mitra).
    last = units[-1]
    if last.consonant and last.vowel == "a" and not last.nasal and len(sounded) >= 2:
        after_cluster = len(units) >= 2 and units[-2].consonant and not units[-2].vowel
        if not (after_cluster and last.consonant in ("r", "y", "v")):
            last.vowel = ""

    # In the middle, between two vowels: समझना -> samajhna. Right to left, and
    # never where it would stack three consonants together (ज़िंदगी keeps its
    # "a": zindagi, not zindgi).
    for i in range(len(units) - 2, 0, -1):
        unit, before, after = units[i], units[i - 1], units[i + 1]
        if (unit.consonant and unit.vowel == "a" and not unit.nasal and not unit.visarga
                and before.vowel and not before.nasal
                and after.consonant and after.vowel):
            unit.vowel = ""


def _spell(units: list[Unit]) -> str:
    out = []
    for i, unit in enumerate(units):
        before = units[i - 1] if i else None
        after = units[i + 1] if i + 1 < len(units) else None
        final = after is None

        consonant = unit.consonant
        # व after a joined consonant is a w: ख़्वाब -> khwaab, not khvaab.
        if consonant == "v" and before and before.consonant and not before.vowel:
            consonant = "w"
        # A vowel standing alone after another vowel glides in with a y:
        # लिए -> liye, गए -> gaye.
        if not consonant and unit.vowel in ("e", "ai") and before and before.vowel:
            consonant = "y"

        out.append(consonant + _vowel(unit, final))
        if unit.nasal:
            out.append("m" if after and after.consonant in LIPS else "n")
        if unit.visarga:
            out.append("h")
    return "".join(out)


def _vowel(unit: Unit, final: bool) -> str:
    """Casual spelling: long vowels are doubled mid-word but not at the end
    (जाना -> jaana, तेरी -> teri), and में reads mein, as it is always written.
    A final long a keeps its length before a nasal: कहाँ -> kahaan."""
    vowel = unit.vowel
    if not final:
        return vowel
    if vowel == "aa":
        return "aa" if unit.nasal else "a"
    if vowel == "ee":
        return "i"
    if vowel == "oo":
        return "u"
    if vowel == "e" and unit.nasal:
        return "ei"
    return vowel
