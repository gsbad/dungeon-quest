import array
import math
import pygame

SAMPLE_RATE = 44100
_FADE_SECONDS = 0.01


def _tone_samples(freq, duration, wave="sine", volume=1.0, sample_rate=SAMPLE_RATE):
    """One constant-frequency note as a flat list of interleaved stereo int16 samples."""
    n = max(1, int(sample_rate * duration))
    fade_n = max(1, int(sample_rate * _FADE_SECONDS))
    samples = []
    phase = 0.0
    step = 2 * math.pi * freq / sample_rate
    for i in range(n):
        s = math.sin(phase) if wave == "sine" else (1.0 if math.sin(phase) >= 0 else -1.0)
        phase += step
        env = 1.0
        if i < fade_n:
            env = i / fade_n
        elif i > n - fade_n:
            env = max(0.0, (n - i) / fade_n)
        val = int(max(-1.0, min(1.0, s * env * volume)) * 32767)
        samples.append(val)
        samples.append(val)
    return samples


def _sweep_samples(freq_start, freq_end, duration, volume=1.0, sample_rate=SAMPLE_RATE):
    """A note that linearly slides from freq_start to freq_end (whoosh/chime effect)."""
    n = max(1, int(sample_rate * duration))
    fade_n = max(1, int(sample_rate * _FADE_SECONDS))
    samples = []
    phase = 0.0
    for i in range(n):
        t = i / max(1, n - 1)
        freq = freq_start + (freq_end - freq_start) * t
        s = math.sin(phase)
        phase += 2 * math.pi * freq / sample_rate
        env = 1.0
        if i < fade_n:
            env = i / fade_n
        elif i > n - fade_n:
            env = max(0.0, (n - i) / fade_n)
        val = int(max(-1.0, min(1.0, s * env * volume)) * 32767)
        samples.append(val)
        samples.append(val)
    return samples


def _build_sound(*segments):
    flat = array.array("h")
    for seg in segments:
        flat.extend(seg)
    return pygame.mixer.Sound(buffer=flat.tobytes())


class AudioManager:
    """
    Owns sound-effect playback and the master mute switch. All SFX are
    synthesized in pure Python (no external audio files, no numpy - same
    "generated in code" philosophy as game/assets.py's sprites), so nothing
    extra needs to be packaged/served for the web build.

    sfx_volume/music_volume are split out (even though there is no music yet)
    so a future options screen can control them independently.
    """

    def __init__(self):
        self.enabled = pygame.mixer.get_init() is not None
        self.muted = False
        self.sfx_volume = 0.6
        self.music_volume = 0.5
        self._sounds = {}
        if self.enabled:
            self._build_sounds()

    def _build_sounds(self):
        sr = pygame.mixer.get_init()[0]
        self._sounds["menu_move"] = _build_sound(
            _tone_samples(880, 0.05, "sine", 0.5, sr)
        )
        self._sounds["menu_select"] = _build_sound(
            _tone_samples(660, 0.05, "sine", 0.6, sr),
            _tone_samples(990, 0.08, "sine", 0.6, sr),
        )
        self._sounds["attack"] = _build_sound(
            _sweep_samples(700, 300, 0.09, 0.6, sr)
        )
        self._sounds["hurt"] = _build_sound(
            _tone_samples(150, 0.15, "square", 0.5, sr)
        )
        self._sounds["pickup"] = _build_sound(
            _sweep_samples(500, 950, 0.15, 0.55, sr)
        )
        self._sounds["victory"] = _build_sound(
            _tone_samples(523, 0.12, "sine", 0.6, sr),
            _tone_samples(659, 0.12, "sine", 0.6, sr),
            _tone_samples(784, 0.22, "sine", 0.6, sr),
        )
        self._sounds["game_over"] = _build_sound(
            _tone_samples(392, 0.16, "square", 0.5, sr),
            _tone_samples(330, 0.16, "square", 0.5, sr),
            _tone_samples(262, 0.30, "square", 0.5, sr),
        )

    def play(self, name):
        if not self.enabled or self.muted:
            return
        snd = self._sounds.get(name)
        if snd is not None:
            snd.set_volume(self.sfx_volume)
            snd.play()

    def toggle_mute(self):
        self.muted = not self.muted


class SoundButton:
    """Always-visible mute toggle icon. Hit-testing is done via the same
    InputManager.tapped_rect() mechanism used for menu options - no custom
    press/drag tracking needed since it's a simple one-shot tap target."""

    def __init__(self, cx, cy, radius=22):
        self.cx = cx
        self.cy = cy
        self.radius = radius

    @property
    def rect(self):
        d = self.radius * 2
        return pygame.Rect(self.cx - self.radius, self.cy - self.radius, d, d)

    def draw(self, surface, muted):
        d = self.radius * 2
        buf = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(buf, (25, 25, 35, 140), (self.radius, self.radius), self.radius)
        pygame.draw.circle(buf, (230, 230, 245, 190), (self.radius, self.radius), self.radius, 2)

        bx, by = self.radius - 7, self.radius
        body_color = (235, 235, 245, 230)
        pygame.draw.polygon(buf, body_color, [
            (bx - 4, by - 5), (bx + 2, by - 5), (bx + 9, by - 11),
            (bx + 9, by + 11), (bx + 2, by + 5), (bx - 4, by + 5),
        ])

        if muted:
            pygame.draw.line(
                buf, (255, 100, 100, 235),
                (self.radius - 3, self.radius - 10), (self.radius + 12, self.radius + 10), 3
            )
        else:
            pygame.draw.arc(
                buf, body_color,
                (self.radius + 1, self.radius - 9, 14, 18), -0.9, 0.9, 2
            )
            pygame.draw.arc(
                buf, body_color,
                (self.radius + 5, self.radius - 6, 9, 12), -0.8, 0.8, 2
            )

        surface.blit(buf, (self.cx - self.radius, self.cy - self.radius))
