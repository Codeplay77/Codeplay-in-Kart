extends Node

const SAVE_PATH := "user://garage.cfg"
const RACE_SCENE := "res://scenes/race.tscn"
const MENU_SCENE := "res://scenes/ui/main_menu.tscn"
const CAREER_SCENE := "res://scenes/ui/career.tscn"
const CUP_RESULTS_SCENE := "res://scenes/ui/cup_results.tscn"

var player_config: Dictionary = KartCatalog.default_config()
var race_settings := {
	"track": "sunset_valley",
	"laps": 3,
	"ai_count": 7,
	"class": 1,
}
## Progresso da carreira: melhores troféus por copa/classe (1 = ouro, 2 = prata, 3 = bronze)
## e peças desbloqueadas ("body:bolt", ...).
var progress := {"trophies": {}, "unlocked": []}
var career := {}
var last_results: Array = []


func _ready() -> void:
	load_garage()


func save_garage() -> void:
	var cf := ConfigFile.new()
	for k: String in player_config:
		cf.set_value("kart", k, player_config[k])
	for k: String in race_settings:
		cf.set_value("race", k, race_settings[k])
	cf.set_value("progress", "trophies", progress.trophies)
	cf.set_value("progress", "unlocked", progress.unlocked)
	var err := cf.save(SAVE_PATH)
	if err != OK:
		push_warning("Não foi possível salvar: %s" % error_string(err))


func load_garage() -> void:
	var cf := ConfigFile.new()
	if cf.load(SAVE_PATH) != OK:
		return
	var defaults := KartCatalog.default_config()
	for k: String in defaults:
		var v: Variant = cf.get_value("kart", k, defaults[k])
		if typeof(v) == typeof(defaults[k]):
			player_config[k] = v
	for k: String in race_settings:
		var v: Variant = cf.get_value("race", k, race_settings[k])
		if typeof(v) == typeof(race_settings[k]):
			race_settings[k] = v
	if not TrackCatalog.TRACKS.has(race_settings.track):
		race_settings.track = "sunset_valley"
	progress.trophies = cf.get_value("progress", "trophies", {})
	progress.unlocked = cf.get_value("progress", "unlocked", [])
	for kind: String in ["body", "wheels", "spoiler"]:
		if not is_part_unlocked(kind, player_config[kind]):
			player_config[kind] = defaults[kind]


func is_part_unlocked(kind: String, id: String) -> bool:
	var cat: Dictionary = KartCatalog.catalog(kind)
	if not cat.has(id):
		return false
	if not cat[id].get("locked", false):
		return true
	return ("%s:%s" % [kind, id]) in progress.unlocked


func part_unlock_cup(kind: String, id: String) -> String:
	var key := "%s:%s" % [kind, id]
	for c: Dictionary in TrackCatalog.CUPS:
		if key in c.rewards:
			return c.name
	return ""


func cup_trophy(cup_id: String, class_idx: int = -1) -> int:
	var t: Dictionary = progress.trophies.get(cup_id, {})
	if class_idx >= 0:
		return int(t.get(str(class_idx), 0))
	var best := 0
	for v: int in t.values():
		if v > 0 and (best == 0 or v < best):
			best = v
	return best


func is_cup_unlocked(index: int) -> bool:
	if index <= 0:
		return true
	return cup_trophy(TrackCatalog.CUPS[index - 1].id) > 0


func is_career() -> bool:
	return not career.is_empty()


func current_track_id() -> String:
	if is_career():
		var cup := TrackCatalog.get_cup(career.cup)
		return cup.tracks[career.race]
	return race_settings.track


func current_class() -> Dictionary:
	var idx: int = career.class if is_career() else int(race_settings.class)
	return TrackCatalog.CLASSES[clampi(idx, 0, TrackCatalog.CLASSES.size() - 1)]


func current_laps() -> int:
	return 3 if is_career() else int(race_settings.laps)


func current_ai_count() -> int:
	return 7 if is_career() else int(race_settings.ai_count)


func start_cup(cup_id: String, class_idx: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	var names := RaceManager.AI_NAMES.duplicate()
	names.shuffle()
	var roster: Array = []
	for i in 7:
		var cfg := KartCatalog.random_config(rng)
		roster.append({"name": names[i], "config": cfg})
	career = {
		"cup": cup_id, "class": class_idx, "race": 0, "roster": roster,
		"points": {}, "history": [],
	}
	goto_scene(RACE_SCENE)


func record_race(results: Array) -> void:
	if not is_career():
		return
	var gained := {}
	for r: Dictionary in results:
		var pts: int = TrackCatalog.POINTS[r.place - 1] if r.place <= TrackCatalog.POINTS.size() else 0
		career.points[r.name] = int(career.points.get(r.name, 0)) + pts
		gained[r.name] = pts
	career.history.append(gained)


func cup_standings() -> Array:
	var rows: Array = []
	for name: String in career.get("points", {}):
		rows.append({"name": name, "points": career.points[name], "is_player": name == player_name()})
	rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.points > b.points)
	return rows


func player_name() -> String:
	return str(player_config.get("driver_name", "Você"))


func is_last_cup_race() -> bool:
	return is_career() and career.race >= TrackCatalog.get_cup(career.cup).tracks.size() - 1


func next_cup_race() -> void:
	career.race += 1
	goto_scene(RACE_SCENE)


## Retorna {place, trophy, new_unlocks: Array[String], standings}.
func finish_cup() -> Dictionary:
	var standings := cup_standings()
	var place := 8
	for i in standings.size():
		if standings[i].is_player:
			place = i + 1
	var cup := TrackCatalog.get_cup(career.cup)
	var trophy := place if place <= 3 else 0
	var new_unlocks: Array = []
	if trophy > 0:
		var t: Dictionary = progress.trophies.get(cup.id, {})
		var key := str(career.class)
		var prev := int(t.get(key, 0))
		if prev == 0 or trophy < prev:
			t[key] = trophy
		progress.trophies[cup.id] = t
		for reward: String in cup.rewards:
			if not reward in progress.unlocked:
				progress.unlocked.append(reward)
				new_unlocks.append(reward)
	save_garage()
	return {"place": place, "trophy": trophy, "new_unlocks": new_unlocks, "standings": standings, "cup": cup}


func leave_career() -> void:
	career = {}


func goto_scene(path: String) -> void:
	get_tree().paused = false
	get_tree().change_scene_to_file.call_deferred(path)
