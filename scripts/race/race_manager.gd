class_name RaceManager
extends Node3D

signal countdown_tick(value: int) # 3, 2, 1, 0 (= VAI!)
signal lap_started(kart: Kart, lap: int)
signal race_finished(results: Array)
signal player_finished(kart: Kart)

const AI_NAMES := ["Nina Turbo", "Rex Pistão", "Duda Faísca", "Caio Drift", "Lia Nitro",
	"Beto Escapamento", "Mel Curva", "Tito Vácuo", "Zoe Ignição", "Gus Rampa"]
const ITEMS_FRONT := {"mine": 5, "orb": 3, "turbo": 2}
const ITEMS_MID := {"mine": 3, "orb": 4, "turbo": 3}
const ITEMS_BACK := {"mine": 1, "orb": 3, "turbo": 6}

var track: Track
var track_id := ""
var karts: Array[Kart] = []
var player: Kart
var camera: KartCamera
var hud: Node
var laps := 3
var race_time := 0.0
var started := false
var finished_all := false
var _countdown := 4.0
var _last_tick := 4
var _start_press_time := -1.0
var _player_finished_at := -1.0
var _wrong_way_time := 0.0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	add_to_group("race_manager")
	_rng.randomize()
	laps = GameState.current_laps()
	track_id = GameState.current_track_id()
	track = TrackCatalog.instantiate(track_id)
	add_child(track)

	var ai_count := clampi(GameState.current_ai_count(), 0, 7)
	var cls := GameState.current_class()
	var skill: float = cls.skill
	var roster: Array = GameState.career.get("roster", [])
	var names := AI_NAMES.duplicate()
	names.shuffle()
	var total := ai_count + 1
	for i in total:
		var k := Kart.new()
		k.name = "Kart%d" % i
		k.race_index = i
		add_child(k)
		k.add_to_group("karts")
		k.class_speed = cls.speed
		var is_player := i == total - 1
		if is_player:
			k.setup(GameState.player_config, str(GameState.player_config.get("driver_name", "Você")))
			player = k
			k.controller = PlayerController.new()
		else:
			if i < roster.size():
				k.setup(roster[i].config, roster[i].name)
			else:
				k.setup(KartCatalog.random_config(_rng), names[i % names.size()])
			k.controller = AIController.new(track, self, skill * _rng.randf_range(0.97, 1.03), _rng.randi())
		k.place_at(track.get_grid_transform(i))
		k.track_offset = track.get_offset(k.global_position)
		k.race_distance = k.track_offset - track.length if k.track_offset > track.length * 0.5 else k.track_offset
		k.last_safe_offset = k.track_offset
		k.lap = floori(k.race_distance / track.length)
		k.item_used.connect(_on_item_used)
		k.got_hit.connect(_on_kart_hit)
		karts.append(k)
		# Faróis à noite (no celular só o do jogador: cada luz pesa muito na GPU).
		if track.theme.get("kart_lights", false) and (k == player or not Settings.is_mobile()):
			_add_headlight(k, k == player)

	for k in karts:
		var engine := EngineAudio.new()
		engine.kart = k
		engine.is_player = k == player
		k.add_child(engine)
	player.wall_hit.connect(func(_k: Kart, impact: float) -> void:
		Sfx.play("crash", randf_range(0.92, 1.05), clampf(-14.0 + impact, -12.0, -2.0))
		camera.shake(clampf(impact / 25.0, 0.15, 0.6))
		InputSetup.rumble(0.3, clampf(impact / 25.0, 0.2, 0.9), 0.22))
	player.boosted.connect(func(_k: Kart) -> void:
		Sfx.play("boost", 1.0, -4.0)
		InputSetup.rumble(0.5, 0.0, 0.3))
	player.drift_level_changed.connect(func(_k: Kart, lvl: int) -> void:
		if lvl > 0:
			Sfx.play("drift_level", 1.0 + lvl * 0.12, -6.0)
			InputSetup.rumble(0.25 + lvl * 0.1, 0.0, 0.1))
	player.item_used.connect(func(_k: Kart, _i: String) -> void: Sfx.play("shoot", 1.0, -4.0))
	lap_started.connect(func(k: Kart, lap: int) -> void:
		if k == player and lap > 1:
			Sfx.play("final_lap" if lap == laps else "lap", 1.0, -3.0 if lap == laps else 0.0))

	camera = KartCamera.new()
	camera.target = player
	add_child(camera)
	camera.current = true
	camera.snap()

	hud = load("res://scripts/ui/hud.gd").new()
	hud.race = self
	add_child(hud)

	Music.play_race(track_id)


func _physics_process(delta: float) -> void:
	if not started:
		_countdown -= delta
		var tick := ceili(_countdown)
		if tick != _last_tick and tick <= 3 and tick > 0:
			_last_tick = tick
			countdown_tick.emit(maxi(tick, 0))
			Sfx.play("beep")
		if _start_press_time < 0.0 and Input.is_action_just_pressed("accelerate"):
			_start_press_time = _countdown
		if _countdown <= 0.0:
			_start_race()
		return
	race_time += delta
	for k in karts:
		_update_progress(k)
	_resolve_kart_contacts()
	_check_stuck(delta)
	_update_places()
	_check_player_extras(delta)
	if _player_finished_at > 0.0 and not finished_all:
		var all_done := karts.all(func(k: Kart) -> bool: return k.finished)
		if all_done or race_time - _player_finished_at > 25.0:
			_finish_race()


func _start_race() -> void:
	started = true
	_last_tick = 0
	countdown_tick.emit(0)
	Sfx.play("go")
	for k in karts:
		k.control_enabled = true
	if _start_press_time > 0.0 and _start_press_time < 0.55:
		player.apply_boost(1.2, 0.9)
	for k in karts:
		if k != player and _rng.randf() < 0.4:
			k.apply_boost(0.9, 0.7)


func _update_progress(k: Kart) -> void:
	var off := track.get_offset(k.global_position)
	var d := off - k.track_offset
	if d < -track.length * 0.5:
		d += track.length
	elif d > track.length * 0.5:
		d -= track.length
	k.track_offset = off
	k.race_distance += d
	var reached := floori(k.race_distance / track.length)
	if reached > k.lap and not k.finished:
		if reached >= 1:
			k.lap_times.append(race_time - _sum(k.lap_times))
		k.lap = reached
		if reached >= laps:
			k.finished = true
			k.finish_time = race_time
			if k == player:
				_player_finished_at = race_time
				Sfx.play("cheer", 1.0, -8.0)
				player.controller = AIController.new(track, self, 0.95, 7)
				player_finished.emit(k)
				Music.play_finish(karts.filter(func(o: Kart) -> bool: return o.finished).size(), karts.size())
		else:
			lap_started.emit(k, reached + 1)

	if k.grounded and k.surface == "road":
		k.last_safe_offset = off
	var center := track.sample(off).origin
	var lateral := Vector2(k.global_position.x - center.x, k.global_position.z - center.z).length()
	var outside := lateral > track.road_width * 0.5 + track.wall_distance + 4.0
	var lost := k.global_position.y < center.y - 15.0 or k.global_position.y < track.liquid_y + 0.2 or (outside and k.grounded)
	if lost or (k == player and Input.is_action_just_pressed("respawn") and k.control_enabled):
		k.respawn(track.get_respawn_transform(k.last_safe_offset))
		if k == player:
			camera.snap.call_deferred()


func _resolve_kart_contacts() -> void:
	for i in karts.size():
		var a := karts[i]
		for j in range(i + 1, karts.size()):
			var b := karts[j]
			var d := b.global_position - a.global_position
			if absf(d.y) > 1.3:
				continue
			d.y = 0.0
			var dist := d.length()
			if dist > 2.2 or dist < 0.001:
				continue
			var n := d / dist
			var reach := a.extent_towards(n) + b.extent_towards(-n)
			if dist >= reach:
				continue
			var approach := (a.linear_velocity - b.linear_velocity).dot(n) # > 0: aproximando
			var j_imp := maxf(approach, 0.0) * 1.15 + (reach - dist) * 7.0
			var total := a.mass + b.mass
			a.bump(-n * j_imp * b.mass / total)
			b.bump(n * j_imp * a.mass / total)
			if approach > 3.0 and (a == player or b == player):
				Sfx.play("bump", randf_range(0.9, 1.1), -4.0)
				camera.shake(0.25)
				InputSetup.rumble(0.35, 0.35, 0.12)


var _stuck_time := 0.0


func _check_stuck(delta: float) -> void:
	if player.finished or not player.control_enabled or not (player.controller is PlayerController):
		_stuck_time = 0.0
		return
	var trying := player.in_throttle > 0.5 or player.in_brake > 0.5
	if trying and absf(player.forward_speed) < 1.5 and player.linear_velocity.length() < 1.5:
		_stuck_time += delta
	else:
		_stuck_time = maxf(0.0, _stuck_time - delta * 2.0)
	if _stuck_time > 3.0:
		_stuck_time = 0.0
		player.respawn(track.get_respawn_transform(player.last_safe_offset))
		camera.snap.call_deferred()


func _sum(a: Array[float]) -> float:
	var s := 0.0
	for x in a:
		s += x
	return s


func _update_places() -> void:
	var order := karts.duplicate()
	order.sort_custom(func(a: Kart, b: Kart) -> bool:
		if a.finished != b.finished:
			return a.finished
		if a.finished:
			return a.finish_time < b.finish_time
		return a.race_distance > b.race_distance)
	for i in order.size():
		(order[i] as Kart).place = i + 1


func _check_player_extras(delta: float) -> void:
	var tf := track.sample(player.track_offset)
	var going_back := player.linear_velocity.dot(-tf.basis.z) < -4.0
	_wrong_way_time = _wrong_way_time + delta if going_back else 0.0


func is_wrong_way() -> bool:
	return _wrong_way_time > 1.0


func finish_now() -> void:
	if not finished_all:
		_finish_race()


func _finish_race() -> void:
	finished_all = true
	for k in karts:
		if not k.finished:
			var remaining := laps * track.length - k.race_distance
			var avg := maxf(k.race_distance / maxf(race_time, 1.0), 10.0)
			k.finish_time = race_time + remaining / avg
	var order := karts.duplicate()
	order.sort_custom(func(a: Kart, b: Kart) -> bool: return a.finish_time < b.finish_time)
	var results: Array = []
	for i in order.size():
		var k: Kart = order[i]
		var best := INF
		for t in k.lap_times:
			best = minf(best, t)
		results.append({
			"place": i + 1, "name": k.driver_name, "time": k.finish_time,
			"best_lap": best, "is_player": k == player, "config": k.config,
		})
	GameState.last_results = results
	if GameState.is_career():
		GameState.record_race(results)
		for r: Dictionary in results:
			r["points"] = GameState.career.history[-1].get(r.name, 0)
	race_finished.emit(results)


func roll_item(k: Kart) -> void:
	k.set_item("rolling")
	if k == player:
		Sfx.play("pickup", 1.0, -3.0)
	var frac := float(k.place - 1) / maxf(karts.size() - 1, 1)
	var table: Dictionary = ITEMS_FRONT if frac < 0.3 else (ITEMS_MID if frac < 0.7 else ITEMS_BACK)
	var total := 0
	for v: int in table.values():
		total += v
	var r := _rng.randi() % total
	var chosen := "turbo"
	for key: String in table:
		r -= int(table[key])
		if r < 0:
			chosen = key
			break
	await get_tree().create_timer(1.1, false).timeout
	if is_instance_valid(k) and k.item == "rolling":
		k.set_item(chosen)
		if k == player:
			Sfx.play("item_ready", 1.0, -3.0)


func _on_item_used(k: Kart, item: String) -> void:
	match item:
		"turbo":
			k.apply_boost(1.6, 1.0)
		"orb":
			OrbProjectile.spawn(self, k)
		"mine":
			MineItem.spawn(self, k)


func _on_kart_hit(k: Kart) -> void:
	if k == player:
		camera.shake(0.8)
		Sfx.play("hit")
		InputSetup.rumble(0.6, 1.0, 0.45)


func player_distance() -> float:
	return player.race_distance if player else 0.0


func kart_ahead(k: Kart, max_dist: float) -> Kart:
	for o in karts:
		if o != k and o.race_distance > k.race_distance and o.race_distance - k.race_distance < max_dist:
			return o
	return null


func kart_behind(k: Kart, max_dist: float) -> Kart:
	for o in karts:
		if o != k and o.race_distance < k.race_distance and k.race_distance - o.race_distance < max_dist:
			return o
	return null


func _add_headlight(k: Kart, is_player: bool) -> void:
	var spot := SpotLight3D.new()
	spot.light_color = Color(1.0, 0.95, 0.85)
	spot.light_energy = 6.0 if is_player else 3.5
	spot.spot_range = 34.0 if is_player else 20.0
	spot.spot_angle = 32.0
	spot.spot_attenuation = 0.8
	spot.shadow_enabled = false
	spot.position = Vector3(0, 0.6, -1.0)
	spot.rotation_degrees.x = -8.0
	k.visual.add_child(spot)


func restart() -> void:
	GameState.goto_scene(GameState.RACE_SCENE)


func to_menu() -> void:
	if GameState.is_career():
		GameState.leave_career()
		GameState.goto_scene(GameState.CAREER_SCENE)
	else:
		GameState.goto_scene(GameState.MENU_SCENE)


func continue_career() -> void:
	if GameState.is_last_cup_race():
		GameState.goto_scene(GameState.CUP_RESULTS_SCENE)
	else:
		GameState.next_cup_race()
