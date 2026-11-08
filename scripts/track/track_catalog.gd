class_name TrackCatalog
extends RefCounted
## Pistas "layout" vêm de TrackLayouts (gerado por tools/track_gen/generate_layouts.py);
## pistas "scene" têm uma cena própria. "overrides" sobrescreve chaves do tema.

const TRACKS := {
	"sunset_valley": {"name": "Vale do Pôr do Sol", "theme": "valley", "scene": "res://scenes/tracks/sunset_valley.tscn"},
	"dunas_douradas": {"name": "Dunas Douradas", "theme": "desert"},
	"praia_coqueiral": {"name": "Praia Coqueiral", "theme": "beach"},
	"bosque_outonal": {"name": "Bosque Outonal", "theme": "autumn"},
	"pico_nevado": {"name": "Pico Nevado", "theme": "snow"},
	"canion_vermelho": {"name": "Cânion Vermelho", "theme": "canyon"},
	"avenida_neon": {"name": "Avenida Neon", "theme": "night"},
	"charneca_nevoa": {"name": "Charneca da Névoa", "theme": "moor"},
	"cratera_ardente": {"name": "Cratera Ardente", "theme": "volcano"},
	"oasis_escondido": {"name": "Oásis Escondido", "theme": "desert", "overrides": {
		"sky": "qwantani_dusk_2_puresky", "sky_energy": 0.5, "sun_color": Color(1.0, 0.68, 0.42), "sun_pitch": -14.0, "sun_yaw": -100.0,
		"fog_color": Color(0.95, 0.66, 0.45), "hill_base": -13.0, "hill_var": 22.0,
		"liquid": "water", "liquid_level": -1.0,
		"scatter": [
			["palm_tree", 230, 1.0, 200.0, 0.8, 1.3, 0.25, true, {}],
			["bush", 160, 0.0, 120.0, 0.7, 1.4, 0.3, false, {}],
			["grass_tuft", 320, 0.0, 110.0, 0.7, 1.5, 0.3, false, {}],
			["cactus_a", 70, 3.0, 220.0, 0.8, 1.3, 0.3, true, {}],
			["rock_mesa", 28, 45.0, 300.0, 0.7, 1.5, 0.0, true, {}],
			["rock_a", 70, 1.0, 250.0, 0.5, 2.0, 0.3, true, {"rock": Color(1.0, 0.8, 0.62), "moss": Color(0.9, 0.75, 0.5)}],
		],
	}},
	"ilha_dos_ventos": {"name": "Ilha dos Ventos", "theme": "beach", "overrides": {
		"sky": "kloofendal_48d_partly_cloudy_puresky", "sky_energy": 0.85, "sun_pitch": -40.0, "sun_yaw": 120.0,
		"hill_base": -14.0, "hill_var": 22.0,
	}},
	"geleira_cristal": {"name": "Geleira Cristal", "theme": "snow", "overrides": {
		"sky": "qwantani_dusk_2_puresky", "sky_energy": 0.5, "sun_color": Color(1.0, 0.76, 0.62), "sun_pitch": -12.0, "sun_yaw": -100.0,
		"fog_color": Color(0.9, 0.78, 0.82), "sun_energy": 1.4,
	}},
	"metropole_noturna": {"name": "Metrópole Noturna", "theme": "night", "overrides": {
		"rail_glow": Color(1.0, 0.15, 0.7), "line_color": Color(1.0, 0.4, 0.85),
		"curb_a": Color(1.0, 0.75, 0.1), "curb_b": Color(0.6, 0.2, 1.0),
	}},
	"desfiladeiro_eco": {"name": "Desfiladeiro do Eco", "theme": "canyon", "overrides": {
		"sky": "industrial_sunset_02_puresky", "sky_energy": 0.45, "sun_color": Color(1.0, 0.62, 0.38), "sun_pitch": -14.0,
		"sun_yaw": -150.0, "fog_color": Color(0.85, 0.5, 0.35), "hill_base": 38.0,
	}},
	"floresta_ancestral": {"name": "Floresta Ancestral", "theme": "autumn", "overrides": {
		"sky": "kloofendal_28d_misty_puresky", "sky_energy": 0.6, "sun_color": Color(1.0, 0.86, 0.7), "sun_pitch": -32.0,
		"fog_color": Color(0.78, 0.72, 0.62), "fog_density": 0.0045, "fog_aerial": 0.85,
		"tint_a": Color(0.6, 0.78, 0.38),
	}},
	"coracao_vulcao": {"name": "Coração do Vulcão", "theme": "volcano", "overrides": {
		"fog_density": 0.0042, "sun_pitch": -10.0, "hill_base": -16.0,
	}},
}

const CUPS := [
	{"id": "brisa", "name": "Copa Brisa", "color": Color("#4fc3f7"),
		"tracks": ["sunset_valley", "dunas_douradas", "praia_coqueiral", "bosque_outonal"],
		"rewards": ["body:bolt", "wheels:retro"]},
	{"id": "trovao", "name": "Copa Trovão", "color": Color("#ffd54f"),
		"tracks": ["pico_nevado", "canion_vermelho", "avenida_neon", "charneca_nevoa"],
		"rewards": ["spoiler:duck", "wheels:neon"]},
	{"id": "vulcao", "name": "Copa Vulcão", "color": Color("#ff7043"),
		"tracks": ["cratera_ardente", "oasis_escondido", "ilha_dos_ventos", "geleira_cristal"],
		"rewards": ["body:mantis", "spoiler:halo"]},
	{"id": "lendaria", "name": "Copa Lendária", "color": Color("#ce93d8"),
		"tracks": ["metropole_noturna", "desfiladeiro_eco", "floresta_ancestral", "coracao_vulcao"],
		"rewards": ["body:titan"]},
]

const CLASSES := [
	{"id": "50", "name": "50cc", "speed": 0.86, "skill": 0.9},
	{"id": "100", "name": "100cc", "speed": 1.0, "skill": 0.97},
	{"id": "150", "name": "150cc", "speed": 1.12, "skill": 1.03},
]

const POINTS := [15, 12, 10, 8, 6, 4, 2, 1]


static func ids() -> Array:
	return TRACKS.keys()


static func get_def(track_id: String) -> Dictionary:
	return TRACKS.get(track_id, TRACKS.sunset_valley)


static func cup_of(track_id: String) -> Dictionary:
	for c: Dictionary in CUPS:
		if track_id in c.tracks:
			return c
	return {}


static func get_cup(cup_id: String) -> Dictionary:
	for c: Dictionary in CUPS:
		if c.id == cup_id:
			return c
	return CUPS[0]


static func instantiate(track_id: String) -> Track:
	var def := get_def(track_id)
	if def.has("scene"):
		return (load(def.scene) as PackedScene).instantiate() as Track
	var t := ThemedTrack.new()
	t.track_id = track_id
	return t
