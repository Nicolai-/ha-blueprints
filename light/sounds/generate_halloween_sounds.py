"""Generate the sound files for the Halloween Motion Effects blueprint.

Pure Python (standard library only). Writes mono 16-bit WAV files to
light/sounds/halloween/. Run: python generate_halloween_sounds.py
"""

import math
import random
import wave
from array import array
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "halloween"
ONE_SHOT_RATE = 22050
LONG_TRACK_RATE = 16000
LONG_TRACK_SECONDS = 300
MAINS_HZ = 50
HEARTBEAT_LEAD_SECONDS = 2.0
HEARTBEAT_RAMP_SECONDS = 120

random.seed(31)


def lowpass(samples, cutoff, rate):
    """One-pole low-pass filter."""
    alpha = 1 - math.exp(-2 * math.pi * cutoff / rate)
    out, y = [], 0.0
    for x in samples:
        y += alpha * (x - y)
        out.append(y)
    return out


def highpass(samples, cutoff, rate):
    low = lowpass(samples, cutoff, rate)
    return [x - l for x, l in zip(samples, low)]


def bandpass(samples, center, q, rate):
    """RBJ biquad band-pass (constant peak gain)."""
    w0 = 2 * math.pi * center / rate
    alpha = math.sin(w0) / (2 * q)
    a0 = 1 + alpha
    b0, b2 = alpha / a0, -alpha / a0
    a1, a2 = -2 * math.cos(w0) / a0, (1 - alpha) / a0
    out, x1, x2, y1, y2 = [], 0.0, 0.0, 0.0, 0.0
    for x in samples:
        y = b0 * x + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x, y1, y
        out.append(y)
    return out


def noise(count):
    return [random.uniform(-1, 1) for _ in range(count)]


def add(target, source, offset=0, gain=1.0):
    for i, s in enumerate(source):
        j = offset + i
        if 0 <= j < len(target):
            target[j] += s * gain


def write_wav(name, samples, rate, peak=0.89):
    """Normalise to the given peak with a soft clip and write a 16-bit WAV."""
    top = max(abs(s) for s in samples) or 1.0
    data = array("h", (int(math.tanh(s / top * 1.2) / math.tanh(1.2) * peak * 32767) for s in samples))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(data.tobytes())
    print(f"{path.name}: {len(samples) / rate:.1f} s, {path.stat().st_size / 1e6:.1f} MB")


def thunder():
    """Sharp crack followed by a rolling, decaying rumble (~8 s)."""
    rate, seconds = ONE_SHOT_RATE, 8.0
    count = int(rate * seconds)
    out = [0.0] * count

    crack_len = int(rate * 0.35)
    crack = highpass(noise(crack_len), 900, rate)
    crack = [s * math.exp(-i / (rate * 0.06)) for i, s in enumerate(crack)]
    add(out, crack, gain=0.8)

    rumble = lowpass(lowpass(noise(count), 180, rate), 120, rate)
    swells = [(random.uniform(0.0, 4.5), random.uniform(0.4, 1.0)) for _ in range(6)]
    for i in range(count):
        t = i / rate
        env = sum(g * math.exp(-max(0.0, t - start) / 1.4) * (1 - math.exp(-max(0.0, t - start) / 0.08))
                  for start, g in swells if t >= start)
        out[i] += rumble[i] * env * 9 * min(1.0, (seconds - t) / 1.5)
    return write_wav("thunder.wav", out, rate)


def scream():
    """Shrieking voice-like glide with vibrato and breath (~2.6 s)."""
    rate, seconds = ONE_SHOT_RATE, 2.6
    count = int(rate * seconds)
    source, phase = [], 0.0
    for i in range(count):
        t = i / rate
        glide = 620 + 520 * min(1.0, t / 0.35) - 260 * max(0.0, t - 1.2) / 1.4
        vibrato = 1 + 0.035 * math.sin(2 * math.pi * 6.5 * t) + random.uniform(-0.01, 0.01)
        phase += glide * vibrato / rate
        saw = 2 * (phase % 1) - 1
        source.append(saw + random.uniform(-0.35, 0.35))
    formants = [(950, 6, 1.0), (1750, 8, 0.7), (2900, 10, 0.45)]
    voiced = [0.0] * count
    for center, q, gain in formants:
        add(voiced, bandpass(source, center, q, rate), gain=gain)
    for i in range(count):
        t = i / rate
        env = min(1.0, t / 0.05) * (1.0 if t < 1.6 else math.exp(-(t - 1.6) / 0.35))
        voiced[i] *= env
    return write_wav("scream.wav", voiced, rate)


def heartbeat_track():
    """Lub-dub heartbeat that speeds up from 2.5 s to 1.5 s per beat over the
    first 2 minutes, then stays at 1.5 s for the rest of the 5 minute track.

    Uses the same beat schedule as the blueprint's heartbeat effect: the first
    beat is 2 s after playback starts and each beat is one period after the
    previous one, with the period taken at the previous beat.
    """
    rate = LONG_TRACK_RATE
    count = rate * LONG_TRACK_SECONDS
    out = [0.0] * count

    def thump(freq, length, gain):
        samples = int(rate * length)
        return [gain * math.sin(2 * math.pi * freq * (1 - 0.3 * i / samples) * i / rate)
                * math.exp(-i / (rate * length / 4)) * min(1.0, i / (rate * 0.004))
                for i in range(samples)]

    lub, dub = thump(55, 0.18, 1.0), thump(68, 0.14, 0.7)
    t = HEARTBEAT_LEAD_SECONDS
    while t < LONG_TRACK_SECONDS - 1:
        progress = min(1.0, (t - HEARTBEAT_LEAD_SECONDS) / HEARTBEAT_RAMP_SECONDS)
        period = 2.5 - 1.0 * progress
        start = int(t * rate)
        add(out, lub, start)
        add(out, dub, start + int(rate * 0.24))
        t += period
    return write_wav("heartbeat.wav", lowpass(out, 400, rate), rate)


def mains_hum(count, rate, wobble_depth=0.25):
    """Buzzing transformer hum built from mains harmonics."""
    harmonics = [(1, 0.5), (2, 1.0), (3, 0.45), (4, 0.35), (6, 0.2), (8, 0.12)]
    out = []
    for i in range(count):
        t = i / rate
        wobble = 1 + wobble_depth * math.sin(2 * math.pi * 0.13 * t) * math.sin(2 * math.pi * 0.71 * t)
        out.append(wobble * sum(g * math.sin(2 * math.pi * MAINS_HZ * h * t) for h, g in harmonics))
    return out


def crackle(rate, length, gain):
    burst = highpass(noise(int(rate * length)), 1500, rate)
    return [s * gain * random.random() ** 3 for s in burst]


def electrical_buzz_track():
    """Faulty-wiring buzz with crackles, sparks and short dropouts (5 minutes)."""
    rate = LONG_TRACK_RATE
    count = rate * LONG_TRACK_SECONDS
    out = mains_hum(count, rate)
    gate = [1.0] * count
    t = 1.0
    while t < LONG_TRACK_SECONDS - 3:
        start = int(t * rate)
        if random.random() < 0.2:
            for i in range(start, min(count, start + int(rate * random.uniform(0.6, 1.8)))):
                gate[i] = 0.05
        else:
            add(out, crackle(rate, random.uniform(0.05, 0.4), random.uniform(2.0, 4.5)), start)
        t += random.uniform(0.6, 2.5)
    smooth_gate = lowpass(gate, 30, rate)
    return write_wav("electrical_buzz.wav", [s * g for s, g in zip(out, smooth_gate)], rate)


def power_failure_track():
    """Repeating power failures: sputtering hum, power-down whine, silence, clunk and surge (5 minutes)."""
    rate = LONG_TRACK_RATE
    count = rate * LONG_TRACK_SECONDS
    hum = mains_hum(count, rate, wobble_depth=0.1)
    out = [0.0] * count
    gain = [0.0] * count

    def fill(start_s, end_s, level):
        for i in range(int(start_s * rate), min(count, int(end_s * rate))):
            gain[i] = level

    t = 0.0
    while t < LONG_TRACK_SECONDS - 2:
        cycle_start = t
        for _ in range(3):  # sputter
            length = random.uniform(0.5, 0.9)
            fill(t, t + length, random.uniform(0.2, 1.0))
            add(out, crackle(rate, 0.15, 3.0), int(t * rate))
            t += length
        fade = 3.0  # power-down whine while the hum fades
        whine_len = int(rate * fade)
        phase, whine = 0.0, []
        for i in range(whine_len):
            progress = i / whine_len
            phase += (420 * (1 - progress) + 30) / rate
            whine.append(math.sin(2 * math.pi * phase) * 0.35 * (1 - progress))
        add(out, whine, int(t * rate))
        for i in range(whine_len):
            j = int(t * rate) + i
            if j < count:
                gain[j] = 1 - i / whine_len
        t += fade + 3.0 + random.uniform(3.0, 6.0)  # darkness
        clunk_len = int(rate * 0.25)
        clunk = [math.sin(2 * math.pi * 70 * i / rate) * math.exp(-i / (rate * 0.03)) * 3 for i in range(clunk_len)]
        add(out, clunk, int(t * rate))
        add(out, crackle(rate, 0.2, 4.0), int(t * rate))
        hold = random.uniform(5.0, 10.0)
        fill(t, t + hold, 1.0)
        t += hold
        if t - cycle_start < 1:
            break
    smooth_gain = lowpass(gain, 40, rate)
    for i in range(count):
        out[i] += hum[i] * smooth_gain[i]
    return write_wav("power_failure.wav", out, rate)


if __name__ == "__main__":
    thunder()
    scream()
    heartbeat_track()
    electrical_buzz_track()
    power_failure_track()
