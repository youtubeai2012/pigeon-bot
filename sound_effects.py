"""Small, quiet sound cues timed to events in the narration."""

import math
import re
import wave

import numpy as np


SAMPLE_RATE = 44100
KEYWORDS = {
    "impact": {"hit", "hits", "struck", "punch", "crash", "crashed", "break", "broke",
               "shattered", "fall", "falls", "fell", "drop", "dropped", "slam", "slammed",
               "explosion", "exploded", "bang"},
    "splash": {"splash", "splashed", "water", "river", "ocean", "sea", "underwater", "rain", "wave"},
    "whoosh": {"fly", "flying", "jump", "jumps", "jumped", "throw", "threw", "launched",
               "spin", "spinning", "spins", "swing", "swinging", "slide", "slid"},
    "fire": {"fire", "flame", "burn", "burned", "burning", "heat", "lava"},
    "chime": {"reveal", "revealed", "discovered", "finally", "suddenly", "secret", "surprise"},
}


def cue(kind, rng):
    seconds = {"impact": 0.38, "splash": 0.60, "whoosh": 0.52,
               "fire": 0.62, "chime": 0.65}[kind]
    t = np.arange(round(seconds * SAMPLE_RATE), dtype=np.float32) / SAMPLE_RATE
    noise = rng.standard_normal(len(t)).astype(np.float32)
    if kind == "impact":
        sound = (np.sin(2 * np.pi * (95 * t - 60 * t * t)) + 0.25 * noise) * np.exp(-11 * t)
    elif kind == "splash":
        sound = noise * np.exp(-5 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 12 * t) ** 2)
    elif kind == "whoosh":
        sound = noise * np.sin(np.pi * t / seconds) ** 2
    elif kind == "fire":
        pops = (rng.random(len(t)) > 0.997).astype(np.float32)
        sound = noise * 0.25 * np.exp(-2 * t) + pops * np.exp(-4 * t)
    else:
        sound = (np.sin(2 * np.pi * 660 * t) + 0.5 * np.sin(2 * np.pi * 990 * t)) * np.exp(-6 * t)
    fade = min(220, len(sound) // 4)
    sound[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    sound[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    peak = max(float(np.max(np.abs(sound))), 1e-6)
    return sound * (0.055 / peak)


def make_effects(words, length, output):
    """Write a low-level mono WAV; return False when there are no matching events."""
    events = []
    for start, _, word in words:
        token = re.sub(r"[^a-z]", "", word.lower())
        kind = next((kind for kind, terms in KEYWORDS.items() if token in terms), None)
        if kind and 0 <= start < length - 0.2 and (not events or start - events[-1][0] >= 4):
            events.append((start, kind))
            if len(events) == 4:
                break
    if not events:
        print("No matching sound cues for this video", flush=True)
        return False

    samples = np.zeros(math.ceil(length * SAMPLE_RATE), dtype=np.float32)
    rng = np.random.default_rng(42)
    for start, kind in events:
        effect = cue(kind, rng)
        offset = round(start * SAMPLE_RATE)
        end = min(len(samples), offset + len(effect))
        samples[offset:end] += effect[:end - offset]
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(output), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())
    print("Quiet sound cues:", ", ".join(f"{kind}@{start:.1f}s" for start, kind in events), flush=True)
    return True
