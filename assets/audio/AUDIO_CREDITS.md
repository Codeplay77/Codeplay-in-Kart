# Audio Credits

The third-party recordings and music listed below are **CC0 1.0 (public domain dedication)**.
https://creativecommons.org/publicdomain/zero/1.0/

The license was checked on each item's own page (OpenGameArt license field, Freesound
license field, Kenney asset page and the bundled License.txt). Credit is not required by CC0.
It is given here as a courtesy and so the origin of each file is easy to trace.

## Audio polish (`refined/`)

Recorded engines, tires, boost, impacts, crowd and UI sounds in `refined/` are
processed derivatives of the corresponding CC0 recordings credited below.
Original files remain untouched. Processing uses high-pass filtering, a broad
upper-mid cut, low-pass filtering, conservative gain and periodic filter warmup
for loops. These derivatives retain their 44.1 kHz sample rate, with 16-bit PCM
WAV storage and **uncompressed Godot imports**; no lost detail is claimed to be
restored from the original lossy previews.

`beep`, `go`, `pickup`, `item_ready`, `drift_level`, `lap`, `finish` and `shoot`
in `refined/` are new synthesized cues authored for this project (CC0), rendered
at 48 kHz with smooth envelopes and layered tones. Reproducible source:
`tools/audio/refine_audio.py`. Measurements: `docs/audio_processing.json`.

Processing done for this project: format conversion to Ogg Vorbis/WAV at 44.1 kHz, gain
normalization (music around -16 LUFS integrated, sfx peak around -3 dBFS), and, for the sfx,
trimming plus seamless loop crossfades. For Freesound items the source is the public HQ
preview of the CC0 sound. Downloading the original file needs a Freesound account.

## Music (`assets/audio/music/`)

All music is by **MintoDog**, from the OpenGameArt collection "For Racing Game (MintoDog's music)".

| Game file | Original title / file | Author | Source | License |
|---|---|---|---|---|
| music/menu_theme.ogg | Racing Game Menu (racing_game_menu_bpm165.ogg) | MintoDog | https://opengameart.org/content/racing-game-menu | CC0 |
| music/race_pure_raceway.ogg | Pure Raceway (pure_raceway_bpm160.ogg) | MintoDog | https://opengameart.org/content/pure-raceway | CC0 |
| music/race_hot_roadway.ogg | Hot Roadway [Remake] (hot_roadway_remake_bpm160.ogg) | MintoDog | https://opengameart.org/content/hot-roadway-remake | CC0 |
| music/race_fever_stadium.ogg | Fever Stadium (fever_stadium_bpm165.ogg) | MintoDog | https://opengameart.org/content/fever-stadium | CC0 |
| music/race_neon_sign_circuit.ogg | Neon sign Circuit [Remake] (neon_sign_circuit_remake_bpm145.ogg) | MintoDog | https://opengameart.org/content/neon-sign-circuit-remake | CC0 |
| music/race_cool_highway.ogg | Cool Highway [Remake] (cool_highway_remake_bpm140.ogg) | MintoDog | https://opengameart.org/content/cool-highway-remake | CC0 |
| music/results_win_loop.ogg | Racing Game Finish & Jingle: "Race Finish Best (Loop)_BPM132" | MintoDog | https://opengameart.org/content/racing-game-finish-jingle | CC0 |
| music/jingle_finish_win.ogg | Racing Game Finish & Jingle: "Race Finish Best (Jingle)" | MintoDog | https://opengameart.org/content/racing-game-finish-jingle | CC0 |
| music/jingle_finish_good.ogg | Racing Game Finish & Jingle: "Race Finish Good (Jingle)" | MintoDog | https://opengameart.org/content/racing-game-finish-jingle | CC0 |
| music/jingle_finish_lose.ogg | Racing Game Finish & Jingle: "Race Finish Bad (Jingle)" | MintoDog | https://opengameart.org/content/racing-game-finish-jingle | CC0 |
| music/jingle_course_intro.ogg | Racing Game Finish & Jingle: "Course Intro (Jingle)" | MintoDog | https://opengameart.org/content/racing-game-finish-jingle | CC0 |
| music/jingle_start_grid.ogg | Racing Game Finish & Jingle: "Start Grid (Jingle)" | MintoDog | https://opengameart.org/content/racing-game-finish-jingle | CC0 |
| music/jingle_final_lap.ogg | Racing Game Finish & Jingle: "Final Lap (Jingle)" | MintoDog | https://opengameart.org/content/racing-game-finish-jingle | CC0 |

## Sound effects (`assets/audio/sfx/`)

| Game file | Original title | Author | Source | License |
|---|---|---|---|---|
| sfx/engine_idle.ogg | Go kart start.wav (idle section cut into a loop) | Hanbaal | https://freesound.org/people/Hanbaal/sounds/178666/ | CC0 |
| sfx/engine_high.ogg | Quad Bike_ATV Engine.wav (steady rev section cut into a loop) | Alex_hears_things (Alex Fitzwater / needle media) | https://freesound.org/people/Alex_hears_things/sounds/379915/ | CC0 |
| sfx/skid_loop.ogg | Chrysler LHS tire squeal 04 (04-25-2009).wav (sustained section cut into a loop) | audible-edge | https://freesound.org/people/audible-edge/sounds/71739/ | CC0 |
| sfx/skid_screech.ogg | screeching tyres / tires (first screech, one-shot) | johnnydekk | https://freesound.org/people/johnnydekk/sounds/614627/ | CC0 |
| sfx/countdown_beep.wav | Race start D4 D5 Square-wave - Dry (first beep) | Sadiquecat | https://freesound.org/people/Sadiquecat/sounds/845658/ | CC0 |
| sfx/countdown_go.wav | Race start D4 D5 Square-wave - Dry (final "go" tone) | Sadiquecat | https://freesound.org/people/Sadiquecat/sounds/845658/ | CC0 |
| sfx/countdown_full.ogg | Race start D4 D5 Square-wave - Dry (complete) | Sadiquecat | https://freesound.org/people/Sadiquecat/sounds/845658/ | CC0 |
| sfx/boost.ogg | Epic whoosh.wav (trimmed) | EcoDTR | https://freesound.org/people/EcoDTR/sounds/27281/ | CC0 |
| sfx/crowd_cheer.ogg | Crowd Cheer (first 10 s, faded out) | FoolBoyMedia | https://freesound.org/people/FoolBoyMedia/sounds/397434/ | CC0 |
| sfx/item_pickup.wav | powerUp2.ogg, from the "Digital Audio" pack | Kenney (kenney.nl) | https://kenney.nl/assets/digital-audio | CC0 |
| sfx/crash.wav | impactPlate_heavy_000.ogg, from the "Impact Sounds" pack | Kenney (kenney.nl) | https://kenney.nl/assets/impact-sounds | CC0 |
| sfx/bump.wav | impactMetal_medium_000.ogg, from the "Impact Sounds" pack | Kenney (kenney.nl) | https://kenney.nl/assets/impact-sounds | CC0 |
| sfx/item_hit.wav | explosionCrunch_000.ogg, from the "Sci-fi Sounds" pack | Kenney (kenney.nl) | https://kenney.nl/assets/sci-fi-sounds | CC0 |
| sfx/ui_select.wav | select_001.ogg, from the "Interface Sounds" pack | Kenney (kenney.nl) | https://kenney.nl/assets/interface-sounds | CC0 |
| sfx/ui_confirm.wav | confirmation_001.ogg, from the "Interface Sounds" pack | Kenney (kenney.nl) | https://kenney.nl/assets/interface-sounds | CC0 |
| sfx/ui_back.wav | back_001.ogg, from the "Interface Sounds" pack | Kenney (kenney.nl) | https://kenney.nl/assets/interface-sounds | CC0 |

---

# Second audio pass (v2)

Everything below is also **CC0 1.0**. The license was checked on each item's own page (the OpenGameArt
"License(s)" field or the Freesound license box). Each item listed here shows CC0 as its only license.
The old files above were kept unchanged.

## Engine loops (`assets/audio/sfx/engine/`)

How they were made: one steady-RPM section per level was cut from the source. A high-pass filter at
about 0.7 x the firing frequency removed the rumble below the engine note. The small pitch drift inside
the section was flattened with a time-varying resample, so each loop holds one steady pitch. The loop
length is a whole number of engine cycles. The loop seam was placed where the waveform matched best and
was smoothed with a short linear crossfade (0.1 to 0.3 s). Output is mono, 44.1 kHz, Ogg Vorbis q6, about
-17 LUFS per loop, so the levels have matched loudness when crossfaded.
"f0" is the measured firing frequency (the fundamental of the engine note). It was measured on the
finished loop with a harmonic-comb FFT fit. To pitch-match two levels during a crossfade, scale the
pitch by the ratio of their f0 values.
All Freesound sources are the public HQ previews (Ogg, about 165 to 192 kbps). Downloading the originals
needs a Freesound account.

### Main set: one BMW 120d engine (4-cylinder turbo-diesel), exterior mics, 4 separate steady-RPM takes

| Game file | f0 | Length | Original title | Author | Source | License |
|---|---|---|---|---|---|---|
| sfx/engine/engine_rpm1.ogg | 27.9 Hz (idle, about 840 rpm) | 1.79 s | SFX_Car_Engine_Outside_Idle.wav | GiocoSound | https://freesound.org/people/GiocoSound/sounds/401552/ | CC0 |
| sfx/engine/engine_rpm2.ogg | 49.3 Hz | 1.30 s | SFX_Car_Engine_Outside_RPMLow.wav | GiocoSound | https://freesound.org/people/GiocoSound/sounds/401556/ | CC0 |
| sfx/engine/engine_rpm3.ogg | 67.0 Hz | 1.82 s | SFX_Car_Engine_Outside_RPMMed.wav | GiocoSound | https://freesound.org/people/GiocoSound/sounds/401555/ | CC0 |
| sfx/engine/engine_rpm4.ogg | 85.0 Hz (about 2550 rpm) | 1.20 s | SFX_Car_Engine_Outside_RPMHigh.wav | GiocoSound | https://freesound.org/people/GiocoSound/sounds/401551/ | CC0 |

Pack: "Car_Sound_BMW_120d", https://freesound.org/people/GiocoSound/packs/22622/

### Alternative set A: one Ford Ranger (2000) engine, held at idle, light throttle and strong throttle (`sfx/engine/alt_4stroke_truck/`)

Source: "Ford Ranger (2000) RPM variations outside 4 mics" by YannSauvin,
https://freesound.org/people/YannSauvin/sounds/779214/ (CC0). Only the left channel of the preview was used
(the front-of-engine mic), so there is no phase cancellation between mics.

| Game file | f0 | Length | Section of source |
|---|---|---|---|
| sfx/engine/alt_4stroke_truck/engine_rpm1.ogg | 28.3 Hz (idle) | 1.98 s | 58.5 to 65.5 s |
| sfx/engine/alt_4stroke_truck/engine_rpm2.ogg | 68.7 Hz | 2.01 s | 85 to 95 s |
| sfx/engine/alt_4stroke_truck/engine_rpm3.ogg | 98.0 Hz | 2.00 s | 150 to 160 s |

### Alternative set B: one Honda CR85 two-stroke dirt bike, recorded on board at high RPM (`sfx/engine/alt_2stroke_bike/`)

Source: "HONDA_85CR.wav" by Olympia_94, https://freesound.org/people/Olympia_94/sounds/704792/ (CC0).

| Game file | f0 | Length | Section of source |
|---|---|---|---|
| sfx/engine/alt_2stroke_bike/engine_rpm1.ogg | 166.8 Hz | 1.00 s | about 41.5 to 42.9 s |
| sfx/engine/alt_2stroke_bike/engine_rpm2.ogg | 182.4 Hz | 1.50 s | about 34.4 to 37.0 s |
| sfx/engine/alt_2stroke_bike/engine_rpm3.ogg | 201.5 Hz | 1.40 s | about 57.0 to 58.8 s |

## Music v2 (`assets/audio/music/v2/`)

How they were made: Ogg Vorbis q5, 44.1 kHz stereo. Only gain was applied, to reach about -16 LUFS integrated.
Two tracks have peaks too close to 0 dBFS to reach -16 LUFS with gain alone, so they were left quieter
and marked in the table. Nothing was trimmed except digital silence: the encoder-delay zeros at the start
of MP3/OGG sources and silence of more than 0.3 s after a fade-out ending.
Files marked "loop" were published as seamless loops. The others end with a fade-out and should be
restarted when they finish.

| Game file | Title | Author | Source | License |
|---|---|---|---|---|
| music/v2/drive.ogg | Drive | Zane Little Music | https://opengameart.org/content/drive-0 | CC0 |
| music/v2/empty_stretch.ogg | Empty Stretch | Zane Little Music | https://opengameart.org/content/empty-stretch | CC0 |
| music/v2/synesthesia.ogg | Synesthesia | Zane Little Music | https://opengameart.org/content/synesthesia | CC0 |
| music/v2/sideways_city.ogg | Sideways City (loop version, sideways_city_loop.wav) | Zane Little Music | https://opengameart.org/content/sideways-city | CC0 |
| music/v2/happy_ukulele_island_surfing.ogg | Happy Ukelele Island Surfing Theme (-19 LUFS, peak-limited) | Tarush Singhal | https://opengameart.org/content/happy-ukelele-island-surfing-theme | CC0 |
| music/v2/black_diamond.ogg | Black Diamond (loop) | Joth | https://opengameart.org/content/black-diamond | CC0 |
| music/v2/raspberry_jam.ogg | Raspberry Jam | congusbongus | https://opengameart.org/content/raspberry-jam | CC0 |
| music/v2/super_wreck_roadway.ogg | Super Wreck Roadway (looping version) | Umplix | https://opengameart.org/content/super-wreck-roadway | CC0 |
| music/v2/microwave.ogg | MicroWave (-20 LUFS, peak-limited) | Fupi | https://opengameart.org/content/microwave-0 | CC0 |
| music/v2/menu_apple_cider.ogg | Apple Cider (loop version, apple_cider_loop.wav), from "Apple Cider Juiced!" | Zane Little Music | https://opengameart.org/content/apple-cider-juiced | CC0 |
| music/v2/podium_funky_victory_loop.ogg | Funky Victory Loop | Archonic | https://opengameart.org/content/funky-victory-loop | CC0 |
