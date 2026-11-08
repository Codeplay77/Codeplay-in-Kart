class_name KartCatalog
extends RefCounted
## Para adicionar uma peça nova: gere o .glb seguindo docs/ASSET_CONTRACT.md e
## adicione uma entrada no dicionário correspondente abaixo.
## Atributos vão de 1 a 10. "offroad" reduz a perda de velocidade fora da pista.

const MODEL_DIR := "res://assets/models/karts/"

const BODIES := {
	"vortex": {
		"name": "Vortex",
		"desc": "Kart de corrida clássico. Equilibrado em tudo.",
		"scene": MODEL_DIR + "body_vortex.glb",
		"stats": {"speed": 5, "accel": 5, "handling": 5, "weight": 5, "offroad": 4},
	},
	"brutus": {
		"name": "Brutus",
		"desc": "Rali off-road. Pesado, robusto e ótimo na terra.",
		"scene": MODEL_DIR + "body_brutus.glb",
		"stats": {"speed": 4, "accel": 5, "handling": 4, "weight": 8, "offroad": 8},
	},
	"falcon": {
		"name": "Falcon",
		"desc": "Protótipo futurista. Muito veloz, mas leve.",
		"scene": MODEL_DIR + "body_falcon.glb",
		"stats": {"speed": 7, "accel": 4, "handling": 5, "weight": 3, "offroad": 3},
	},
	"bolt": {
		"name": "Bolt",
		"desc": "Hot-rod retrô com motor cromado. Arranca como um foguete.",
		"scene": MODEL_DIR + "body_bolt.glb", "locked": true,
		"stats": {"speed": 5, "accel": 8, "handling": 5, "weight": 5, "offroad": 4},
	},
	"mantis": {
		"name": "Mantis",
		"desc": "Caçador angular. Curvas na ponta da faca.",
		"scene": MODEL_DIR + "body_mantis.glb", "locked": true,
		"stats": {"speed": 6, "accel": 5, "handling": 8, "weight": 4, "offroad": 4},
	},
	"titan": {
		"name": "Titã",
		"desc": "Monstro blindado. Ninguém tira você da pista.",
		"scene": MODEL_DIR + "body_titan.glb", "locked": true,
		"stats": {"speed": 7, "accel": 4, "handling": 4, "weight": 10, "offroad": 8},
	},
}

const WHEELS := {
	"classic": {
		"name": "Slick Clássico",
		"scene": MODEL_DIR + "wheel_classic.glb",
		"stats": {"speed": 0, "accel": 0, "handling": 1, "weight": 0, "offroad": 0},
	},
	"offroad": {
		"name": "Cravo Off-road",
		"scene": MODEL_DIR + "wheel_offroad.glb",
		"stats": {"speed": -1, "accel": 1, "handling": 0, "weight": 1, "offroad": 3},
	},
	"turbine": {
		"name": "Turbina",
		"scene": MODEL_DIR + "wheel_turbine.glb",
		"stats": {"speed": 1, "accel": -1, "handling": 0, "weight": 0, "offroad": -1},
	},
	"retro": {
		"name": "Raio Retrô",
		"scene": MODEL_DIR + "wheel_retro.glb", "locked": true,
		"stats": {"speed": 0, "accel": 2, "handling": 0, "weight": 0, "offroad": -1},
	},
	"neon": {
		"name": "Neon",
		"scene": MODEL_DIR + "wheel_neon.glb", "locked": true,
		"stats": {"speed": 1, "accel": 0, "handling": 1, "weight": 0, "offroad": -1},
	},
}

const SPOILERS := {
	"none": {
		"name": "Nenhum",
		"scene": "",
		"stats": {"speed": 0, "accel": 1, "handling": -1, "weight": -1, "offroad": 0},
	},
	"wing": {
		"name": "Asa Clássica",
		"scene": MODEL_DIR + "spoiler_wing.glb",
		"stats": {"speed": 0, "accel": 0, "handling": 1, "weight": 0, "offroad": 0},
	},
	"twin": {
		"name": "Asa Dupla",
		"scene": MODEL_DIR + "spoiler_twin.glb",
		"stats": {"speed": -1, "accel": 0, "handling": 2, "weight": 1, "offroad": 0},
	},
	"fin": {
		"name": "Barbatana",
		"scene": MODEL_DIR + "spoiler_fin.glb",
		"stats": {"speed": 1, "accel": 0, "handling": 0, "weight": 0, "offroad": 0},
	},
	"duck": {
		"name": "Rabo de Pato",
		"scene": MODEL_DIR + "spoiler_duck.glb", "locked": true,
		"stats": {"speed": 1, "accel": 1, "handling": 0, "weight": 0, "offroad": 0},
	},
	"halo": {
		"name": "Halo",
		"scene": MODEL_DIR + "spoiler_halo.glb", "locked": true,
		"stats": {"speed": 0, "accel": 0, "handling": 2, "weight": -1, "offroad": 0},
	},
}

const DRIVER_SCENE := MODEL_DIR + "driver.glb"

const PALETTE: Array[Color] = [
	Color("#e8202a"), Color("#ff6a00"), Color("#ffc400"), Color("#9be600"),
	Color("#18c46a"), Color("#00c2c7"), Color("#1e7bff"), Color("#2b2fd9"),
	Color("#8a2be2"), Color("#ff3fa4"), Color("#f4f4f4"), Color("#9aa0a8"),
	Color("#3a3f47"), Color("#121316"), Color("#7a4a26"), Color("#d4af37"),
]

const COLOR_SLOTS := {
	"color_primary": "Pintura principal",
	"color_secondary": "Pintura secundária",
	"color_accent": "Detalhes",
	"color_rim": "Aros",
	"color_suit": "Macacão",
	"color_helmet": "Capacete",
}

const MATERIAL_SLOTS := {
	"paint_primary": "color_primary",
	"paint_secondary": "color_secondary",
	"paint_accent": "color_accent",
	"rim": "color_rim",
	"suit": "color_suit",
	"helmet": "color_helmet",
}

const STAT_KEYS := ["speed", "accel", "handling", "weight", "offroad"]
const STAT_LABELS := {
	"speed": "Velocidade", "accel": "Aceleração", "handling": "Controle",
	"weight": "Peso", "offroad": "Off-road",
}


static func catalog(kind: String) -> Dictionary:
	match kind:
		"body":
			return BODIES
		"wheels":
			return WHEELS
		"spoiler":
			return SPOILERS
	return {}


static func default_config() -> Dictionary:
	return {
		"driver_name": "Você",
		"body": "vortex",
		"wheels": "classic",
		"spoiler": "wing",
		"color_primary": Color("#e8202a"),
		"color_secondary": Color("#f4f4f4"),
		"color_accent": Color("#ffc400"),
		"color_rim": Color("#9aa0a8"),
		"color_suit": Color("#1e7bff"),
		"color_helmet": Color("#f4f4f4"),
	}


static func random_config(rng: RandomNumberGenerator) -> Dictionary:
	var c := default_config()
	c.body = BODIES.keys()[rng.randi() % BODIES.size()]
	c.wheels = WHEELS.keys()[rng.randi() % WHEELS.size()]
	c.spoiler = SPOILERS.keys()[rng.randi() % SPOILERS.size()]
	for slot: String in COLOR_SLOTS:
		c[slot] = PALETTE[rng.randi() % PALETTE.size()]
	while (c.color_secondary as Color).is_equal_approx(c.color_primary):
		c.color_secondary = PALETTE[rng.randi() % PALETTE.size()]
	return c


static func compute_stats(config: Dictionary) -> Dictionary:
	var out := {}
	var parts: Array = [
		BODIES.get(config.get("body", "vortex"), BODIES.vortex),
		WHEELS.get(config.get("wheels", "classic"), WHEELS.classic),
		SPOILERS.get(config.get("spoiler", "none"), SPOILERS.none),
	]
	for key: String in STAT_KEYS:
		var total := 0
		for p: Dictionary in parts:
			total += int(p.stats.get(key, 0))
		out[key] = clampi(total, 1, 10)
	return out
