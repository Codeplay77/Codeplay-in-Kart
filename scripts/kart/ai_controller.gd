class_name AIController
extends RefCounted

var track: Track
var race: Node
var skill := 1.0 # 0.85 (fácil) .. 1.05 (difícil)
var rng := RandomNumberGenerator.new()

var _lane := 0.0
var _lane_target := 0.0
var _lane_timer := 0.0
var _progress_timer := 0.0
var _progress_ref := -INF
var _fails := 0
var _reverse_time := 0.0
var _item_timer := 0.0
var _drift_hold := 0.0


func _init(track_: Track, race_: Node, skill_: float, seed_: int) -> void:
	track = track_
	race = race_
	skill = skill_
	rng.seed = seed_
	_lane_target = rng.randf_range(-0.45, 0.45)
	_lane = _lane_target


func update(kart: Kart, delta: float) -> void:
	if track == null:
		return
	var speed := kart.forward_speed
	var off := kart.track_offset
	var half := track.road_width * 0.5

	_lane_timer -= delta
	if _lane_timer <= 0.0:
		_lane_timer = rng.randf_range(2.0, 5.0)
		_lane_target = rng.randf_range(-0.5, 0.5)
	_lane = move_toward(_lane, _lane_target, delta * 0.25)

	var look := 7.0 + absf(speed) * 0.55
	var target_xf := track.sample(off + look)
	var target := target_xf.origin + target_xf.basis.x * (_lane * half)
	var fwd := kart.get_forward()
	var to_target := target - kart.global_position
	to_target -= kart.ground_normal * to_target.dot(kart.ground_normal)
	var angle := fwd.signed_angle_to(to_target.normalized(), kart.ground_normal)
	# signed_angle_to é positivo para a esquerda; o volante é positivo para a direita.
	var steer := clampf(-angle * 2.4, -1.0, 1.0)

	var far_xf := track.sample(off + look + 18.0)
	var here_xf := track.sample(off)
	var bend := (-here_xf.basis.z).signed_angle_to(-far_xf.basis.z, Vector3.UP)

	var throttle := 1.0
	var brake := 0.0
	if absf(angle) > 0.7 and speed > 18.0:
		throttle = 0.3

	var drift := false
	if kart.drift_dir != 0:
		_drift_hold += delta
		drift = true
		if angle * kart.drift_dir > 0.3:
			drift = false
		if absf(bend) < 0.15 and _drift_hold > 0.8:
			drift = false
		if kart.drift_level >= 3 and absf(bend) < 0.3:
			drift = false
	else:
		_drift_hold = 0.0
		if absf(bend) > 0.5 and speed > 18.0 and absf(angle) < 0.25 and rng.randf() < 0.06 * skill:
			drift = true
			steer = -signf(bend)

	if _reverse_time <= 0.0:
		_progress_timer += delta
	if _progress_timer > 1.5:
		_progress_timer = 0.0
		if kart.control_enabled and kart.spin_time <= 0.0 and kart.race_distance - _progress_ref < 4.0:
			_fails += 1
			if _fails >= 3:
				_fails = 0
				kart.respawn(track.get_respawn_transform(kart.last_safe_offset))
			else:
				_reverse_time = 0.9
		else:
			_fails = 0
		_progress_ref = kart.race_distance
	if _reverse_time > 0.0:
		_reverse_time -= delta
		if _reverse_time <= 0.0:
			_progress_ref = kart.race_distance
		throttle = 0.0
		brake = 1.0
		steer = -steer
		drift = false

	kart.in_throttle = throttle
	kart.in_brake = brake
	kart.in_steer = steer
	kart.in_drift = drift
	kart.speed_multiplier = _rubber_band(kart) * skill

	if kart.item != "":
		_item_timer -= delta
		if _item_timer <= 0.0:
			if _should_use_item(kart):
				kart.in_item = true
			_item_timer = rng.randf_range(0.4, 1.2)
	else:
		_item_timer = rng.randf_range(0.8, 2.5)


func _should_use_item(kart: Kart) -> bool:
	match kart.item:
		"turbo":
			return kart.grounded and kart.drift_dir == 0
		"orb":
			return race.has_method("kart_ahead") and race.kart_ahead(kart, 45.0) != null or rng.randf() < 0.15
		"mine":
			return race.has_method("kart_behind") and race.kart_behind(kart, 25.0) != null or rng.randf() < 0.2
	return true


func _rubber_band(kart: Kart) -> float:
	if race == null or not race.has_method("player_distance"):
		return 1.0
	var gap: float = race.player_distance() - kart.race_distance
	return clampf(1.0 + gap * 0.0006, 0.94, 1.07)
