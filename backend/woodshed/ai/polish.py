"""The complete, correct lyrics of a recording - with Gemini listening, and
the audio itself checking every change.

What Whisper heard has the right *timing* but some words wrong and, worse,
some lines missing altogether (it drops passages it is unsure of). Pasted
lyrics have the right *words* but not this recording's structure. So:

    ① gather   the vocal stem (as audio), Whisper's lines with timings, the
               stretches where singing was heard but nothing transcribed, and
               any pasted lyrics
    ② Gemini   listens and reads, and decides for every heard line - keep,
               correct, or not lyrics (talk) - and inserts every line it hears
               that Whisper missed, with its time
    ③ check    every change against the audio with the forced aligner: words
               not really sung in that place cannot score well
    ④ retry    rejected suggestions go back once, with the reason
    ⑤ re-time  every word, precisely

The LLM proposes; the audio decides. A suggestion the aligner does not
support is dropped and the line keeps what was heard - so the result can only
ever be what was heard, or something the audio confirms.

What is sent to Google: the vocal stem as a small MP3, and lyrics text. Only
when asked for, per song.
"""

import copy
import difflib
import re
import tempfile
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from ..audio import encoding
from ..audio.analysis import lyrics as lyrics_analysis
from ..audio.analysis import roman
from ..audio.analysis.source import load_mono
from ..config import settings
from ..storage import storage
from . import gemini

# A word Whisper gave less than this confidence is flagged to the model.
UNSURE_BELOW = 0.5

# The audio check (see lyrics.Aligner.fit).
#
# A correction is compared with what was heard in the same place: on "Channa
# Mereya", good corrections fitted 0.39-0.81, the bad chorus-over-a-fragment
# replacements 0.07-0.24. It must fit at least CORRECT_MIN and not much worse
# than the heard text.
CORRECT_MIN = 0.35
CORRECT_MARGIN = 0.20
#
# An inserted line has nothing heard to compare with, and a fixed score is not
# enough: in dense talking ANY text fits 0.43-0.52, because there are speech
# sounds everywhere to latch onto. So it is compared with its own letters
# scrambled, in the same place. Measured over three songs: true lines beat
# their scramble by +0.18 to +0.49, fake ones by at most +0.15.
INSERT_MIN = 0.30
INSERT_LEAD = 0.17

SECTIONS = {"intro", "verse", "pre-chorus", "chorus", "bridge", "hook", "outro", "talk", "other"}


class LyricsMismatch(ValueError):
    """Pasted lyrics that do not seem to belong to this song."""

    def __init__(self, score: float, by_model: bool = False):
        self.score = score
        self.by_model = by_model
        super().__init__(
            "The AI judged these lyrics to be a different song" if by_model else
            f"These lyrics don't seem to match this song "
            f"(only {score:.0%} of the phrases heard appear in them)")


# ---- the shape of the answer -----------------------------------------------------------

class Decision(BaseModel):
    action: Literal["keep", "correct", "not_lyrics", "insert"] = Field(
        description="keep / correct / not_lyrics for a heard line; insert for a sung line "
                    "the transcription missed.")
    heard_line: int | None = Field(
        default=None, description="For keep, correct and not_lyrics: the H number. Null for insert.")
    start_seconds: float | None = Field(
        default=None, description="For insert: when the line starts in the audio, in seconds.")
    end_seconds: float | None = Field(
        default=None, description="For insert: when the line ends in the audio, in seconds.")
    text: str = Field(description="The line exactly as sung, in Roman letters. For keep and "
                                  "not_lyrics: the heard text, unchanged.")
    section: str = Field(description="intro, verse, pre-chorus, chorus, bridge, hook, outro, "
                                     "talk or other.")
    pasted_line: int | None = Field(
        default=None, description="The P number of the pasted lyric line this matches, if any.")


class Answer(BaseModel):
    matches_song: bool = Field(
        description="False only if the pasted lyrics are clearly a different song from the "
                    "one sung. True when no lyrics were pasted.")
    lines: list[Decision] = Field(description="Every decision, in the order it occurs in the audio.")


SYSTEM = """\
You are an expert transcriber of Hindi, Urdu and Hinglish songs - film songs, pop, ghazals and live \
performances. You listen carefully, you know how lyrics in this language are written in Roman letters, \
and you never guess.

You are given the separated vocal track of one recording, a machine transcription of it with timings, \
the stretches where singing was detected but nothing was transcribed, and sometimes the song's written \
lyrics, pasted by the user. You produce the complete, accurate lyrics of what is actually sung in this \
recording, line by line, in order.

Every change you make is checked against the audio by a forced aligner, word by word. A suggestion the \
audio does not support is rejected and the line keeps what was heard. So a precise answer beats a \
complete-looking one: change or add only what you can actually hear.\
"""

INSTRUCTIONS = """\
=== YOUR TASK ===

Based on the vocal track and the material above, write the complete lyrics of what is sung in this \
recording.

1. For EVERY heard line (H0, H1, ...), output exactly one decision:
   - "keep": the heard text is right. Small spelling differences count as right - do not rewrite a line \
just to restyle it. Copy the heard text unchanged.
   - "correct": you can hear that some words are different from the heard text. Give exactly what is \
sung. If the line is in the pasted lyrics, use their wording and spelling.
   - "not_lyrics": speech (a host, judges, a singer talking), applause, crowd noise, or sounds that are \
not words of the song. Copy the heard text unchanged and use section "talk".

2. Then find every line that is SUNG but MISSING from the heard lines, and add an "insert" decision for \
each one, with start_seconds and end_seconds as exact as you can hear them. Look especially:
   - inside the G stretches (singing with nothing transcribed),
   - for repeats: if a chorus is sung four times but transcribed twice, the missing ones are inserts,
   - between heard lines that leave a line of the pasted lyrics out.
   Never insert a line you cannot hear. Humming, "aa", "oo", alaap and vocalising are not lines - do \
not insert them.

=== RULES ===

- ORDER: list decisions in the order they happen in the audio, inserts in their place among the heard lines.
- WHAT IS SUNG, NOT WHAT IS WRITTEN: the pasted lyrics are the reference for wording and spelling only. \
Follow this recording: its repeats, its order, its omissions, its ad-libs. A pasted line that is not sung \
here must not appear.
- LINE BOUNDARIES: a corrected line contains only what is sung within that heard line's time span. Do not \
pull words in from a neighbouring line, and never "complete" a fragment with words that are not sung \
there. If a heard line is half of a longer pasted line, correct only the half that is sung in it.
- FRAGMENTS: a short or garbled heard line (one or two words, a held note, a sound) is NOT a place to put \
a whole lyric line. Correct it only if you can hear those exact words there; otherwise keep it, or mark \
it "not_lyrics" if it is not a word of the song.
- MINIMAL CHANGE: never paraphrase. Never change a word you cannot hear is different. When unsure \
between keep and correct, choose keep.
- SPELLING: Roman letters, casual Hindi/Urdu as typed online: "dil", "pyaar", "zindagi", "mohabbat", \
"mein", "hain", "nahin", "kahaan", "kyun", "tujhe", "duaaon", "zikr", "zubaan". When lyrics are pasted, \
follow their spelling. Write z, f, q, kh only where the word has them. Spell the same word the same way \
every time. English words stay in English.
- SECTIONS: label each line intro, verse, pre-chorus, chorus, bridge, hook, outro, talk or other. The \
chorus is the part that comes back with the same words; label all its repeats "chorus".
- pasted_line: the P number of the pasted line you matched, when there is one.
- matches_song: false only if the pasted lyrics are clearly a different song from the one sung.

=== EXAMPLES (illustrations, not from this recording) ===

- H4 heard "tere bina gujaara" [1:02.4-1:05.0], pasted P3 "Tere bina guzaara" -> correct: \
"Tere bina guzaara" (pasted spelling), pasted_line 3.
- H9 heard "Kise hamaari najdi kyon ke" [2:36.1-2:40.0], pasted P12 "Kisse humari nazdeekiyon ke" -> \
correct: "Kisse humari nazdeekiyon ke".
- H15 heard "Jada" [5:31.2-5:32.1], one word over a long held note -> keep "Jada" (or not_lyrics if it \
is not a word). Do NOT replace it with the chorus line.
- H20 heard "Main philm teri" [2:25.5-2:27.0], and the pasted lyrics have nothing like it -> keep it \
unless you can clearly hear different words.
- Singing in G2 [3:08.0-3:26.0], where you hear the chorus line "Channa mereya mereya" twice -> two \
inserts: one with start_seconds 188.5 end_seconds 192.0, one with 192.4 to 196.1, both pasted_line 5.
- H40 heard "Thank you so much" [5:56.8-5:58.1], a judge speaking -> not_lyrics, section "talk".\
"""


# ---- the steps ---------------------------------------------------------------------------

def polish(track_id: str, pasted: str | None = None, force: bool = False) -> dict:
    """Complete and correct a song's lyrics, save the result, and return it.

    Raises LyricsMismatch for pasted lyrics from a different song (unless
    `force`), and gemini.AIUnavailable when the model cannot be reached.
    """
    data = lyrics_analysis.load(track_id)
    if not data or not data["lines"]:
        raise ValueError("this song has no lyrics to correct")

    # Always work from what Whisper heard, never from an earlier correction.
    heard = data.get("heardLines") or copy.deepcopy(data["lines"])
    for line in heard:
        line.pop("corrected", None)
        line.pop("talk", None)
    pasted = (pasted or "").strip() or None

    score = None
    if pasted:
        score = match_score(heard, pasted)
        if score < settings.lyrics_match_threshold and not force:
            raise LyricsMismatch(score)

    audio = load_mono(track_id, ("Vocals",), lyrics_analysis.WHISPER_RATE).astype(np.float32)
    gaps = lyrics_analysis.find_gaps(heard, audio)
    prompt = _prompt(heard, gaps, pasted)
    sound = _vocal_mp3(track_id)

    answer = gemini.generate(gemini_system(), prompt, Answer, audio=sound)
    if pasted and not answer.matches_song and not force:
        raise LyricsMismatch(score or 0.0, by_model=True)

    aligner = lyrics_analysis.Aligner()
    try:
        lines, stats, rejected = _check(heard, answer, audio, aligner)
        retried = False
        if rejected:
            # One more chance, told exactly what the audio did not support.
            retried = True
            answer = gemini.generate(gemini_system(), prompt + _feedback(rejected), Answer, audio=sound)
            lines, stats, rejected = _check(heard, answer, audio, aligner)

        data["heardLines"] = heard
        data["lines"] = lines
        data["polish"] = {"model": settings.llm_model, "audio": True, "pasted": bool(pasted),
                          "match": None if score is None else round(score, 3),
                          **stats, "rejected": len(rejected), "retried": retried,
                          "changedLines": stats["corrected"] + stats["inserted"]}

        _retime_corrected(lines, audio, aligner)
        lyrics_analysis._hold_line_ends(lines, lyrics_analysis._loudness(audio))
        data["aligned"] = True
    finally:
        aligner.close()

    storage.write_json(track_id, lyrics_analysis.LYRICS_FILE, data)
    return data


def restore(track_id: str) -> dict | None:
    """Undo a correction: back to exactly what Whisper heard."""
    data = lyrics_analysis.load(track_id)
    if not data or "heardLines" not in data:
        return data
    data["lines"] = data.pop("heardLines")
    data.pop("polish", None)
    storage.write_json(track_id, lyrics_analysis.LYRICS_FILE, data)
    return data


def gemini_system() -> str:
    return SYSTEM


# ---- what Gemini is given ------------------------------------------------------------------

def _vocal_mp3(track_id: str) -> bytes:
    """The vocal stem as a small mono MP3 - what Gemini listens to."""
    with tempfile.TemporaryDirectory() as folder:
        out = encoding.compact_mp3(storage.path(track_id, "Vocals.wav"), Path(folder) / "vocals.mp3")
        return out.read_bytes()


def _prompt(heard: list[dict], gaps: list[tuple[float, float]], pasted: str | None) -> str:
    """The material first, the instructions last - as Google advises when the
    input is large."""
    rows = []
    for i, line in enumerate(heard):
        row = f'H{i} [{_clock(line["start"])}-{_clock(line["end"])}] "{_text(line)}"'
        original = " ".join(w.get("heard", "") for w in line["words"]).strip()
        if original and original != _text(line):
            row += f' | original: "{original}"'
        unsure = [w["text"] for w in line["words"] if w.get("p", 1.0) < UNSURE_BELOW]
        if unsure:
            row += f" | unsure: {', '.join(unsure)}"
        rows.append(row)

    parts = ["=== THE VOCAL TRACK ===\nThe audio above is the separated vocal of the recording. "
             "Times below are in minutes:seconds from its start.",
             "=== HEARD LINES (machine transcription, with timings) ===\n" + "\n".join(rows)]

    if gaps:
        parts.append("=== SINGING DETECTED, NOTHING TRANSCRIBED ===\n"
                     + "\n".join(f"G{j} [{_clock(a)}-{_clock(b)}]" for j, (a, b) in enumerate(gaps)))
    else:
        parts.append("=== SINGING DETECTED, NOTHING TRANSCRIBED ===\n(none found)")

    if pasted:
        numbered = [f"P{k} {line.strip()}" for k, line in
                    enumerate(l for l in pasted.splitlines() if l.strip())]
        parts.append("=== PASTED LYRICS (the song as written - possibly a different version) ===\n"
                     + "\n".join(numbered))
    else:
        parts.append("=== PASTED LYRICS ===\n(none - work from the audio and the heard lines alone)")

    return "\n\n".join(parts) + "\n\n" + INSTRUCTIONS


def _feedback(rejected: list[str]) -> str:
    return ("\n\n=== CHECK RESULTS FOR YOUR PREVIOUS ANSWER ===\n"
            "These suggestions were checked against the audio by a forced aligner and rejected: the "
            "words were not found sung at that place.\n"
            + "\n".join(f"- {r}" for r in rejected)
            + "\n\nGive your complete answer again. For each rejected suggestion, either fix it - the "
              "right time, or the words actually sung there - or drop it (keep the heard line as heard; "
              "do not insert). Everything else may stay the same.")


# ---- checking the answer against the audio ----------------------------------------------------

def _check(heard: list[dict], answer: Answer, audio, aligner) -> tuple[list[dict], dict, list[str]]:
    """Apply the decisions that the audio supports; list the ones it does not."""
    song_end = len(audio) / lyrics_analysis.WHISPER_RATE
    by_heard: dict[int, Decision] = {}
    inserts: list[Decision] = []
    for decision in answer.lines:
        if decision.action == "insert":
            inserts.append(decision)
        elif decision.heard_line is not None and 0 <= decision.heard_line < len(heard):
            by_heard.setdefault(decision.heard_line, decision)

    lines, rejected = [], []
    stats = {"corrected": 0, "inserted": 0, "talk": 0}

    for i, line in enumerate(heard):
        out = copy.deepcopy(line)
        decision = by_heard.get(i)
        if decision is None:
            lines.append(out)
            continue
        out["section"] = _section(decision.section)

        if decision.action == "not_lyrics":
            out["talk"] = True
            out["section"] = "talk"
            stats["talk"] += 1
        elif decision.action == "correct" and _differs(decision.text, line):
            lo, hi = max(0.0, line["start"] - 0.5), min(song_end, line["end"] + 0.5)
            before = aligner.fit(audio, _text(line), lo, hi)
            after = aligner.fit(audio, decision.text, lo, hi)
            if after >= CORRECT_MIN and after >= before - CORRECT_MARGIN:
                out["words"] = _spread(decision.text.split(), line["start"], line["end"])
                out["corrected"] = True
                stats["corrected"] += 1
            else:
                rejected.append(f'H{i} correct -> "{decision.text}": not supported by the audio '
                                f"(fit {after:.2f}; the heard text fits {before:.2f})")
        lines.append(out)

    placed: list[dict] = []
    for decision in inserts:
        line, problem = _insert(decision, heard, audio, aligner, song_end, placed)
        if line:
            placed.append(line)
            stats["inserted"] += 1
        else:
            rejected.append(problem)

    return sorted(lines + placed, key=lambda l: l["start"]), stats, rejected


def _retime_corrected(lines: list[dict], audio, aligner) -> None:
    """Precise word times for corrected lines only.

    Untouched lines keep the times they already have, on purpose: aligning an
    already-timed line a second time is not stable on long held words - its
    window shifts slightly, and a held "Besabriyaa...n" moved from 35.3s to
    38.8s when re-run. Inserted lines were timed when they were checked.
    """
    song_end = len(audio) / lyrics_analysis.WHISPER_RATE
    margin = lyrics_analysis.ALIGN_MARGIN_SECONDS
    for i, line in enumerate(lines):
        if not line.get("corrected"):
            continue
        lo = max(line["start"] - margin, lines[i - 1]["end"] if i else 0.0)
        hi = min(line["end"] + margin, lines[i + 1]["start"] if i + 1 < len(lines) else song_end)
        try:
            found = aligner.place(audio, [w["text"] for w in line["words"]], lo, hi)
        except Exception:  # noqa: BLE001 - keeps its provisional, evenly spread times
            continue
        for word, timed in zip(line["words"], found):
            if timed:
                word["start"], word["end"] = timed[0], timed[1]
        line["start"], line["end"] = line["words"][0]["start"], line["words"][-1]["end"]


def _insert(decision: Decision, heard: list[dict], audio, aligner, song_end: float,
            placed: list[dict]) -> tuple[dict | None, str]:
    """A missed line, if the audio confirms it is sung where Gemini says."""
    words = decision.text.split()
    label = f'insert "{decision.text}" at {_clock(decision.start_seconds or 0)}'
    if not words or decision.start_seconds is None or decision.end_seconds is None \
            or decision.end_seconds <= decision.start_seconds:
        return None, f"{label}: no usable start and end time"

    # Never on top of something Whisper heard: if a heard line is there, the
    # right move is to correct that line, not to add another beside it.
    for i, line in enumerate(heard):
        overlap = min(line["end"], decision.end_seconds) - max(line["start"], decision.start_seconds)
        if overlap > 0.3:
            return None, (f"{label}: heard line H{i} is already at that time "
                          f"(correct H{i} instead, or give the right time)")

    # Look a second either side of where Gemini heard it, up to the
    # neighbouring heard lines.
    lo = max(0.0, decision.start_seconds - 1.0)
    hi = min(song_end, decision.end_seconds + 1.0)
    for line in heard:
        if line["end"] <= decision.start_seconds:
            lo = max(lo, line["end"])
        elif line["start"] >= decision.end_seconds:
            hi = min(hi, line["start"])
    if hi - lo < 0.8:
        return None, f"{label}: no room there between the heard lines"

    found = aligner.place(audio, words, lo, hi)
    scores = [f[2] for f in found if f]
    fit = float(np.mean(scores)) if scores else 0.0
    scrambled = aligner.fit(audio, " ".join(w[::-1] for w in reversed(words)), lo, hi)
    if fit < INSERT_MIN or fit - scrambled < INSERT_LEAD:
        return None, (f"{label}: not found sung there (fit {fit:.2f}; "
                      f"the same letters scrambled fit {scrambled:.2f})")

    times = [f for f in found if f]
    start, end = times[0][0], times[-1][1]
    if any(min(end, p["end"]) - max(start, p["start"]) > 0.5 * (end - start) for p in placed):
        return None, f"{label}: overlaps another inserted line"

    spread = _spread(words, start, end)
    timed = [{"text": w, "start": f[0], "end": f[1]} if f else s for w, f, s in zip(words, found, spread)]
    timed[0]["text"] = timed[0]["text"][:1].upper() + timed[0]["text"][1:]
    return {"start": start, "end": end, "words": timed, "section": _section(decision.section),
            "inserted": True}, ""


# ---- small helpers ----------------------------------------------------------------------------

def match_score(lines: list[dict], pasted: str) -> float:
    """What share of the word *pairs* heard ("dil hai", "tere bina") also
    appear in the pasted lyrics.

    Pairs, not single words: songs in one language share their everyday words
    ("hai", "mera", "dil"), so on single words a different song still scored
    30%. Different songs almost never share word pairs. Measured: the same
    song 69-100% (even with half the lines pasted, or spelt differently), a
    different song 2-3%. A pair counts if a close spelling is there too.
    """
    heard = [pair for line in lines for pair in _pairs(_text(line))]
    if not heard:
        return 0.0
    pasted_pairs = {pair for line in pasted.splitlines() for pair in _pairs(line)}
    found = sum(1 for pair in heard
                if pair in pasted_pairs
                or difflib.get_close_matches(pair, pasted_pairs, n=1, cutoff=0.8))
    return found / len(heard)


def word_error_rate(lines: list[dict], truth: str) -> float:
    """The share of words wrong, against lyrics known to be correct (WER).

    The fewest word insertions, deletions and substitutions turning what we
    have into the truth, divided by the number of words in the truth. 0.0 is
    perfect. Spelling variants of a word ("guzaara" / "gujaara") count as
    right: spelling Roman Hindi is a matter of taste.
    """
    ours = [w for line in lines if not line.get("talk") for w in _words(_text(line))]
    want = _words(truth)
    if not want:
        return 0.0
    cost = list(range(len(want) + 1))
    for i in range(1, len(ours) + 1):
        diagonal, cost[0] = cost[0], i
        for j in range(1, len(want) + 1):
            above = cost[j]
            cost[j] = min(cost[j] + 1, cost[j - 1] + 1,
                          diagonal + (0 if _same(ours[i - 1], want[j - 1]) else 1))
            diagonal = above
    return cost[-1] / len(want)


def missing_lines(lines: list[dict], truth: str) -> float:
    """The share of the correct lyrics' lines that appear nowhere in ours -
    the measure of lines dropped, which word error rate blurs together with
    misheard words."""
    want = [l for l in truth.splitlines() if _words(l)]
    ours = [" ".join(_words(_text(l))) for l in lines if not l.get("talk")]
    if not want:
        return 0.0
    missing = sum(1 for l in want
                  if not difflib.get_close_matches(" ".join(_words(l)), ours, n=1, cutoff=0.6))
    return missing / len(want)


def _text(line: dict) -> str:
    return " ".join(w["text"] for w in line["words"])


def _words(text: str) -> list[str]:
    """Lowercase Roman words; Devanagari is converted first, so either script works."""
    return re.findall(r"[a-z']+", roman.romanise(text).lower())


def _pairs(line: str) -> list[str]:
    words = _words(line)
    return [f"{a} {b}" for a, b in zip(words, words[1:])]


def _same(a: str, b: str) -> bool:
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def _differs(text: str, line: dict) -> bool:
    return _words(text) != _words(_text(line))


def _section(name: str) -> str:
    name = (name or "").strip().lower()
    return name if name in SECTIONS else "other"


def _spread(words: list[str], start: float, end: float) -> list[dict]:
    """Provisional times, evenly across a span - replaced by the aligner's."""
    step = (end - start) / max(len(words), 1)
    out = [{"text": w, "start": round(start + k * step, 3), "end": round(start + (k + 1) * step, 3)}
           for k, w in enumerate(words)]
    if out:
        out[0]["text"] = out[0]["text"][:1].upper() + out[0]["text"][1:]
    return out


def _clock(seconds: float) -> str:
    minutes, rest = divmod(max(0.0, seconds), 60)
    return f"{int(minutes)}:{rest:04.1f}"
