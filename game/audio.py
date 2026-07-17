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
        # Stage H7: a dedicated channel for the looping title-screen theme,
        # reserved via set_reserved() so pygame's automatic channel
        # allocation for one-shot SFX (play()) never steals or gets stolen
        # by it - the two systems can't collide.
        self._music_channel = None
        if self.enabled:
            self._build_sounds()
            pygame.mixer.set_reserved(1)
            self._music_channel = pygame.mixer.Channel(0)

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

        # Stage H7 - one distinct attack cue per common mob archetype
        # (game/enemy.py's ENEMY_FLAVOR keys) and per boss (game/boss.py's
        # BOSS_PATTERNS keys), so combat reads as "something specific just
        # hit/shot at you" instead of the single generic `attack` sfx above
        # (which stays as the player's own swing). Same synthesis
        # primitives as everything above, just more of them - negligible
        # extra boot-time cost, no extra shipped bytes either way.
        # etypes match game/enemy.py's ENEMY_FLAVOR keys as of the
        # "individualization pass" (20 common mobs, per-level rosters) -
        # skeleton/goblin/dark_knight are the original 3 (still spawn on
        # levels 1-3), the rest replaced swamp_troll/cursed_mage/
        # crypt_wraith/ash_fiend/royal_guard one-for-one per level slot.
        self._sounds["attack_skeleton"] = _build_sound(_tone_samples(330, 0.08, "square", 0.4, sr))
        self._sounds["attack_goblin"] = _build_sound(_sweep_samples(500, 750, 0.06, 0.4, sr))
        self._sounds["attack_dark_knight"] = _build_sound(_sweep_samples(320, 160, 0.1, 0.5, sr))
        # Level 5 - Pantano Sombrio
        self._sounds["attack_aranha"] = _build_sound(
            _tone_samples(700, 0.03, "square", 0.35, sr),
            _tone_samples(650, 0.03, "square", 0.35, sr),
        )
        self._sounds["attack_serpente"] = _build_sound(_sweep_samples(600, 900, 0.08, 0.4, sr))
        self._sounds["attack_treant"] = _build_sound(_tone_samples(140, 0.18, "square", 0.5, sr))
        # Level 6 - Torre Amaldicoada
        self._sounds["attack_troll"] = _build_sound(_tone_samples(110, 0.16, "square", 0.5, sr))
        self._sounds["attack_death_knight"] = _build_sound(_sweep_samples(280, 150, 0.1, 0.5, sr))
        # Level 7 - Cripta Perdida
        self._sounds["attack_zumbi"] = _build_sound(_sweep_samples(200, 120, 0.2, 0.45, sr))
        self._sounds["attack_verme"] = _build_sound(_tone_samples(90, 0.1, "square", 0.4, sr))
        self._sounds["attack_imp"] = _build_sound(_sweep_samples(700, 1000, 0.06, 0.4, sr))
        # Level 9 - Salao dos Ecos
        self._sounds["attack_dark_horse"] = _build_sound(_sweep_samples(400, 250, 0.08, 0.45, sr))
        self._sounds["attack_acolito"] = _build_sound(_sweep_samples(350, 700, 0.14, 0.4, sr))
        self._sounds["attack_feiticeira"] = _build_sound(_sweep_samples(500, 950, 0.12, 0.4, sr))
        # Level 10 - Abismo de Cinzas
        self._sounds["attack_fire_hound"] = _build_sound(
            _tone_samples(550, 0.04, "square", 0.4, sr),
            _tone_samples(480, 0.04, "square", 0.4, sr),
        )
        self._sounds["attack_ogro"] = _build_sound(_tone_samples(80, 0.22, "square", 0.6, sr))
        self._sounds["attack_elemental_pedra"] = _build_sound(_tone_samples(70, 0.25, "square", 0.5, sr))
        # Level 11 - Corredor Final
        self._sounds["attack_chimera"] = _build_sound(
            _tone_samples(120, 0.1, "square", 0.5, sr),
            _tone_samples(400, 0.12, "sine", 0.4, sr),
        )
        self._sounds["attack_lyzardman"] = _build_sound(_sweep_samples(450, 300, 0.07, 0.45, sr))
        self._sounds["attack_dark_skeleton"] = _build_sound(_sweep_samples(320, 190, 0.08, 0.5, sr))

        self._sounds["attack_orc_warlord"] = _build_sound(_tone_samples(90, 0.2, "square", 0.6, sr))
        self._sounds["attack_necromancer"] = _build_sound(_sweep_samples(200, 100, 0.25, 0.5, sr))
        self._sounds["attack_shadow_king"] = _build_sound(
            _tone_samples(150, 0.1, "square", 0.5, sr),
            _tone_samples(500, 0.15, "sine", 0.5, sr),
        )
        self._sounds["attack_cacodemon"] = _build_sound(
            _tone_samples(130, 0.12, "square", 0.6, sr),
            _sweep_samples(200, 100, 0.1, 0.5, sr),
        )
        # Stage Q2: Atos 4-6 + boss secreto.
        self._sounds["attack_ursa_ancestral"] = _build_sound(_tone_samples(75, 0.22, "square", 0.6, sr))
        self._sounds["attack_imperatriz_aranha"] = _build_sound(_sweep_samples(650, 950, 0.07, 0.4, sr))
        self._sounds["attack_barao_sanguinario"] = _build_sound(_sweep_samples(220, 110, 0.2, 0.5, sr))
        self._sounds["attack_colosso_runico"] = _build_sound(
            _tone_samples(60, 0.28, "square", 0.6, sr),
            _tone_samples(400, 0.1, "sine", 0.4, sr),
        )
        self._sounds["attack_arquibruxa"] = _build_sound(_sweep_samples(400, 800, 0.15, 0.45, sr))
        self._sounds["attack_senhor_da_alcateia"] = _build_sound(_tone_samples(95, 0.14, "square", 0.6, sr))
        self._sounds["attack_dragao_primordial"] = _build_sound(
            _tone_samples(110, 0.18, "square", 0.6, sr),
            _sweep_samples(300, 700, 0.12, 0.5, sr),
        )

        # Stage H7 - a short looping title-screen theme. No music file
        # exists (or ever will, per this project's "everything generated
        # in code" rule - see the class docstring) so this is a synthesized
        # melody played on a loop (play_music()) rather than
        # pygame.mixer.music, which expects a real file/stream.
        notes = [523, 587, 659, 784, 659, 587, 523, 392]
        self._sounds["title_theme"] = _build_sound(
            *[_tone_samples(n, 0.28, "sine", 0.35, sr) for n in notes]
        )

    def play(self, name):
        if not self.enabled or self.muted:
            return
        snd = self._sounds.get(name)
        if snd is not None:
            snd.set_volume(self.sfx_volume)
            snd.play()

    def play_music(self, name):
        if not self.enabled or self._music_channel is None:
            return
        snd = self._sounds.get(name)
        if snd is None:
            return
        self._music_channel.set_volume(0.0 if self.muted else self.music_volume)
        self._music_channel.play(snd, loops=-1)

    def stop_music(self):
        if self._music_channel is not None:
            self._music_channel.stop()

    def toggle_mute(self):
        self.muted = not self.muted
        if self._music_channel is not None and self._music_channel.get_busy():
            self._music_channel.set_volume(0.0 if self.muted else self.music_volume)


class SoundButton:
    """Always-visible mute toggle icon. Hit-testing is done via the same
    InputManager.tapped_rect() mechanism used for menu options - no custom
    press/drag tracking needed since it's a simple one-shot tap target."""

    def __init__(self, cx, cy, radius=22):
        self.cx = cx
        self.cy = cy
        self.radius = radius
        # Extended-session freeze fix (see game/theme.py's font() cache for
        # the original diagnosis of this exact class of bug): this button
        # is drawn EVERY frame, on EVERY screen, for the entire session
        # (GameStateManager.draw() calls it unconditionally, not gated by
        # GameplayState like paperdoll/items/etc.) - a brand new Surface
        # per frame here is worse than font()'s per-call-site churn ever
        # was, since it's truly universal. Only `muted` (2 states) ever
        # changes what gets drawn, so cache by that instead of rebuilding.
        self._cache = {}

    @property
    def rect(self):
        d = self.radius * 2
        return pygame.Rect(self.cx - self.radius, self.cy - self.radius, d, d)

    def draw(self, surface, muted):
        cached = self._cache.get(muted)
        if cached is None:
            cached = self._render(muted)
            self._cache[muted] = cached
        surface.blit(cached, (self.cx - self.radius, self.cy - self.radius))

    def _render(self, muted):
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
        return buf
