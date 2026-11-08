class_name Kart
extends RigidBody3D
## A colisão é uma esfera (robusta contra paredes e outros karts). A rotação do corpo
## rígido é travada: a direção do kart é controlada por `yaw`, e a velocidade é
## recomposta a cada passo em componentes frente/lateral/normal ao chão, o que dá
## controle preciso de aderência, drift e turbo.

signal item_changed(kart: Kart, item: String)
signal item_used(kart: Kart, item: String)
signal drift_level_changed(kart: Kart, level: int)
signal boosted(kart: Kart)
signal got_hit(kart: Kart)
signal wall_hit(kart: Kart, impact: float)

const RADIUS := 0.5
const LAYER_TRACK := 1
const LAYER_KART := 2
const LAYER_ITEMS := 4

const GRAVITY_AIR := 32.0
const GRAVITY_STICK := 26.0
const MAX_LAUNCH := 9.0
const DRIFT_MIN_SPEED := 9.0
const DRIFT_LEVELS := [0.85, 1.8, 2.9] # segundos de drift para cada nível
const DRIFT_COLORS := [Color(0.9, 0.9, 1.0), Color(0.25, 0.65, 3.0), Color(3.0, 1.2, 0.1), Color(2.0, 0.3, 3.0)]
const DRIFT_BOOST := [[0.0, 0.0], [0.65, 0.6], [1.15, 0.8], [1.8, 1.0]] # [duração, força]

var config: Dictionary = {}
var driver_name := "Piloto"
var stats: Dictionary = {}
var max_speed := 32.0
var accel := 22.0
var turn_rate := 2.2
var offroad_factor := 0.6
var speed_multiplier := 1.0
var class_speed := 1.0

var controller: Object
var control_enabled := false
var in_throttle := 0.0
var in_brake := 0.0
var in_steer := 0.0
var in_drift := false
var in_item := false

var yaw := 0.0
var ground_normal := Vector3.UP
var grounded := false
var air_time := 0.0
var surface := "road"
var forward_speed := 0.0
var drift_dir := 0
var drift_charge := 0.0
var drift_level := 0
var boost_time := 0.0
var boost_power := 0.0
var spin_time := 0.0
var item := ""
var visual: KartVisual

var race_index := 0
var lap := 0
var race_distance := 0.0
var track_offset := 0.0
var place := 1
var finished := false
var finish_time := 0.0
var lap_times: Array[float] = []
var last_safe_offset := 0.0

var _boost_kick := false
var _teleport: Variant = null
var _bump := Vector3.ZERO
var _wall_cooldown := 0.0
var _spin_visual := 0.0
var _hop_visual := 0.0
var _drift_visual := 0.0
var _lean := 0.0
var _visual_basis := Basis.IDENTITY
var _fx_sparks: Array[GPUParticles3D] = []
var _fx_boost: Array[GPUParticles3D] = []
var _fx_dust: Array[GPUParticles3D] = []


func _init() -> void:
	mass = 150.0
	gravity_scale = 0.0
	can_sleep = false
	continuous_cd = true
	axis_lock_angular_x = true
	axis_lock_angular_y = true
	axis_lock_angular_z = true
	collision_layer = LAYER_KART
	collision_mask = LAYER_TRACK # kart x kart é resolvido pela corrida (Kart.bump), com hitbox no formato do kart
	contact_monitor = true
	max_contacts_reported = 4
	var pm := PhysicsMaterial.new()
	pm.friction = 0.0
	pm.bounce = 0.15
	physics_material_override = pm
	var cs := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = RADIUS
	cs.shape = sphere
	add_child(cs)
	visual = KartVisual.new()
	visual.name = "Visual"
	add_child(visual)


func setup(cfg: Dictionary, name_: String) -> void:
	config = cfg.duplicate()
	driver_name = name_
	stats = KartCatalog.compute_stats(cfg)
	max_speed = (27.0 + stats.speed * 1.3) * class_speed
	accel = (13.0 + stats.accel * 2.2) * lerpf(1.0, class_speed, 0.7)
	turn_rate = 1.75 + stats.handling * 0.09
	offroad_factor = 0.42 + stats.offroad * 0.045
	mass = 110.0 + stats.weight * 14.0
	visual.build(cfg)
	_setup_fx()


func place_at(xform: Transform3D) -> void:
	global_transform = Transform3D(Basis.IDENTITY, xform.origin + xform.basis.y * (RADIUS + 0.05))
	var f := -xform.basis.z
	yaw = atan2(-f.x, -f.z)
	ground_normal = xform.basis.y
	_visual_basis = _heading_basis(ground_normal)
	visual.basis = _visual_basis
	visual.position = -ground_normal * RADIUS
	linear_velocity = Vector3.ZERO
	reset_physics_interpolation()


func respawn(xform: Transform3D) -> void:
	_teleport = xform
	drift_dir = 0
	drift_charge = 0.0
	drift_level = 0
	spin_time = 0.0
	boost_time = 0.0


func set_item(i: String) -> void:
	item = i
	item_changed.emit(self, item)


func apply_boost(duration: float, power: float) -> void:
	if spin_time > 0.0:
		return
	boost_time = maxf(boost_time, duration)
	boost_power = maxf(boost_power, power)
	_boost_kick = true
	boosted.emit(self)


func hit() -> void:
	if spin_time > 0.0:
		return
	spin_time = 1.3
	_cancel_drift(false)
	boost_time = 0.0
	got_hit.emit(self)


func bump(dv: Vector3) -> void:
	_bump += dv


func extent_towards(dir: Vector3) -> float:
	var f := Vector3(-sin(yaw), 0.0, -cos(yaw))
	return lerpf(0.72, 1.05, absf(f.dot(dir)))


func is_boosting() -> bool:
	return boost_time > 0.0


func get_forward() -> Vector3:
	var flat := Vector3(-sin(yaw), 0.0, -cos(yaw))
	return (flat - ground_normal * flat.dot(ground_normal)).normalized()


func _physics_process(delta: float) -> void:
	if controller and controller.has_method("update"):
		controller.update(self, delta)
	if not control_enabled:
		in_throttle = 0.0
		in_brake = 0.0
		in_steer = 0.0
		in_drift = false
		in_item = false
	if in_item and item != "" and item != "rolling" and spin_time <= 0.0 and control_enabled:
		var used := item
		set_item("")
		item_used.emit(self, used)
	in_item = false
	_update_visual(delta)


func _integrate_forces(state: PhysicsDirectBodyState3D) -> void:
	var dt := state.step
	if _teleport != null:
		var xf: Transform3D = _teleport
		_teleport = null
		state.transform = Transform3D(Basis.IDENTITY, xf.origin + xf.basis.y * (RADIUS + 0.3))
		state.linear_velocity = Vector3.ZERO
		var f := -xf.basis.z
		yaw = atan2(-f.x, -f.z)
		ground_normal = xf.basis.y
		reset_physics_interpolation.call_deferred()
		return

	var pos := state.transform.origin
	var v := state.linear_velocity

	_wall_cooldown = maxf(0.0, _wall_cooldown - dt)
	for c in state.get_contact_count():
		var obj := state.get_contact_collider_object(c)
		if obj and obj.get_meta("surface", "") == "wall":
			var impact := -v.dot(state.get_contact_local_normal(c))
			if impact > 5.0 and _wall_cooldown <= 0.0:
				_wall_cooldown = 0.4
				wall_hit.emit(self, impact)

	var probe_dir := -ground_normal if grounded else Vector3.DOWN
	var q := PhysicsRayQueryParameters3D.create(pos, pos + probe_dir * (RADIUS + 0.45), LAYER_TRACK, [get_rid()])
	var hit_info := state.get_space_state().intersect_ray(q)
	var was_grounded := grounded
	grounded = not hit_info.is_empty() and (hit_info.position as Vector3).distance_to(pos) < RADIUS + 0.2
	if grounded:
		var n: Vector3 = hit_info.normal
		ground_normal = ground_normal.slerp(n, 1.0 - exp(-18.0 * dt)).normalized()
		var col: Object = hit_info.collider
		surface = col.get_meta("surface", "road") if col else "road"
		air_time = 0.0
	else:
		air_time += dt
		if was_grounded:
			var up_v := v.dot(Vector3.UP)
			if up_v > MAX_LAUNCH:
				v -= Vector3.UP * (up_v - MAX_LAUNCH)
		ground_normal = ground_normal.slerp(Vector3.UP, 1.0 - exp(-3.0 * dt)).normalized()

	var n_up := ground_normal
	var fwd := get_forward()
	var right := fwd.cross(n_up).normalized()
	var spd := v.dot(fwd)
	var lat := v.dot(right)
	var vn := v.dot(n_up)

	var throttle := in_throttle
	var brake := in_brake
	var steer := in_steer
	if spin_time > 0.0:
		spin_time -= dt
		throttle = 0.0
		brake = 0.0
		steer = 0.0

	if drift_dir == 0 and in_drift and grounded and spin_time <= 0.0 and spd > DRIFT_MIN_SPEED and absf(steer) > 0.3:
		drift_dir = 1 if steer > 0.0 else -1
		lat -= drift_dir * minf(spd * 0.12, 3.5)
		drift_charge = 0.0
		drift_level = 0
	if drift_dir != 0:
		if not in_drift or spd < DRIFT_MIN_SPEED * 0.6 or spin_time > 0.0:
			_cancel_drift(in_drift == false and spin_time <= 0.0)
		elif grounded:
			var tight := clampf(steer * drift_dir, -1.0, 1.0)
			drift_charge += dt * (1.0 + 0.6 * maxf(tight, 0.0))
			var lvl := 0
			for i in DRIFT_LEVELS.size():
				if drift_charge >= DRIFT_LEVELS[i]:
					lvl = i + 1
			if lvl != drift_level:
				drift_level = lvl
				drift_level_changed.emit(self, drift_level)

	if drift_dir != 0:
		# Drift: o volante ajusta o raio (aberto ~90 m, neutro ~35 m, fechado ~20 m a 32 m/s).
		var tight := clampf(steer * drift_dir, -1.0, 1.0)
		var factor := lerpf(0.42, 0.78, tight) if tight >= 0.0 else lerpf(0.42, 0.16, -tight)
		yaw -= drift_dir * turn_rate * factor * clampf(absf(spd) / 12.0, 0.4, 1.0) * dt
	elif grounded:
		var speed_factor := clampf(absf(spd) / 7.0, 0.0, 1.0)
		var hi_speed := lerpf(1.0, 0.62, clampf(absf(spd) / max_speed, 0.0, 1.0))
		yaw -= steer * turn_rate * speed_factor * hi_speed * signf(spd if absf(spd) > 0.1 else 1.0) * dt
	else:
		yaw -= steer * turn_rate * 0.45 * dt
	yaw = wrapf(yaw, -PI, PI)

	if boost_time > 0.0:
		boost_time -= dt
		if boost_time <= 0.0:
			boost_power = 0.0

	fwd = get_forward()
	right = fwd.cross(n_up).normalized()

	if grounded:
		var top := max_speed * speed_multiplier
		if surface == "grass" and boost_time <= 0.0:
			top *= offroad_factor
		if boost_time > 0.0:
			top *= 1.0 + 0.32 * boost_power
		if _boost_kick:
			spd = maxf(spd, max_speed * speed_multiplier * (1.0 + 0.18 * boost_power))
		if throttle > 0.05:
			if spd < top:
				var a := accel * (1.0 - 0.55 * clampf(spd / top, 0.0, 1.0)) * throttle
				if spd < 0.0:
					a += 30.0
				if boost_time > 0.0:
					a += 35.0
				spd = minf(spd + a * dt, top)
			else:
				spd = move_toward(spd, top, 10.0 * dt)
		elif brake > 0.05:
			if spd > 0.5:
				spd -= 38.0 * brake * dt
			else:
				spd = maxf(spd - 14.0 * brake * dt, -max_speed * 0.35)
		else:
			spd = move_toward(spd, 0.0, (5.0 if surface == "road" else 14.0) * dt)
			if spd > top:
				spd = move_toward(spd, top, 10.0 * dt)
		if spin_time > 0.0:
			spd = move_toward(spd, 0.0, 28.0 * dt)
		spd += Vector3.DOWN.dot(fwd) * 9.8 * 0.45 * dt
		var grip := 85.0 if drift_dir == 0 else 7.0
		if spin_time > 0.0:
			grip = 20.0
		lat = move_toward(lat, 0.0, grip * dt)
		if drift_dir != 0:
			lat = clampf(lat, -9.0, 9.0)
		vn -= GRAVITY_STICK * dt
		v = fwd * spd + right * lat + n_up * vn
	else:
		v += Vector3.DOWN * GRAVITY_AIR * dt
		if boost_time > 0.0:
			v += fwd * 12.0 * dt
	_boost_kick = false

	if not was_grounded and grounded and air_time == 0.0:
		_hop_visual = maxf(_hop_visual, 0.35)

	if _bump != Vector3.ZERO:
		v += _bump
		_bump = Vector3.ZERO
	forward_speed = v.dot(fwd)
	state.linear_velocity = v


func _cancel_drift(reward: bool) -> void:
	if reward and drift_level > 0:
		var b: Array = DRIFT_BOOST[drift_level]
		apply_boost(b[0], b[1])
	drift_dir = 0
	drift_charge = 0.0
	if drift_level != 0:
		drift_level = 0
		drift_level_changed.emit(self, 0)


func _heading_basis(up: Vector3) -> Basis:
	var fwd := Vector3(-sin(yaw), 0.0, -cos(yaw))
	fwd = (fwd - up * fwd.dot(up)).normalized()
	var right := fwd.cross(up).normalized()
	return Basis(right, up, -fwd).orthonormalized()


func _update_visual(delta: float) -> void:
	var target := _heading_basis(ground_normal)
	_visual_basis = _visual_basis.slerp(target, 1.0 - exp(-14.0 * delta)).orthonormalized()
	_drift_visual = lerpf(_drift_visual, drift_dir * 0.42, 1.0 - exp(-8.0 * delta))
	if spin_time > 0.0:
		_spin_visual += delta * TAU * 2.2
	else:
		_spin_visual = lerpf(_spin_visual, roundf(_spin_visual / TAU) * TAU, 1.0 - exp(-10.0 * delta))
	var lean_target := -in_steer * clampf(absf(forward_speed) / max_speed, 0.0, 1.0) * 0.07
	if drift_dir != 0:
		lean_target = -drift_dir * 0.1
	_lean = lerpf(_lean, lean_target, 1.0 - exp(-6.0 * delta))
	_hop_visual = maxf(0.0, _hop_visual - delta * 3.5)
	var hop_y := sin(_hop_visual * PI) * 0.22
	var extra := Basis(Vector3.UP, -_drift_visual + _spin_visual) * Basis(Vector3.BACK, _lean)
	visual.basis = _visual_basis * extra
	visual.position = -ground_normal * RADIUS + ground_normal * hop_y
	var steer_vis := in_steer
	if drift_dir != 0:
		steer_vis = clampf(drift_dir * 0.6 + in_steer * 0.4, -1.0, 1.0)
	visual.animate(delta, forward_speed, steer_vis)
	_update_fx()


func _setup_fx() -> void:
	for p in _fx_sparks + _fx_boost + _fx_dust:
		p.queue_free()
	_fx_sparks.clear()
	_fx_boost.clear()
	_fx_dust.clear()
	for s: Node3D in visual.rear_wheel_sockets:
		var sp := _make_particles(36, 0.22, 0.055, Vector3(0, 1.4, 1), 2.5, 5.5, -14.0)
		s.add_child(sp)
		sp.position = Vector3(0, -0.24, 0.1)
		_fx_sparks.append(sp)
		var dust := _make_particles(24, 0.7, 0.35, Vector3(0, 1, 1), 1.0, 2.5, 1.0)
		(dust.process_material as ParticleProcessMaterial).color = Color(0.45, 0.36, 0.22, 0.55)
		(dust.process_material as ParticleProcessMaterial).scale_min = 0.6
		(dust.process_material as ParticleProcessMaterial).scale_max = 1.6
		s.add_child(dust)
		dust.position = Vector3(0, -0.24, 0.15)
		_fx_dust.append(dust)
	for e: Node3D in visual.get_exhaust_points():
		var fl := _make_particles(40, 0.22, 0.16, Vector3(0, 0.15, 1), 3.0, 6.0, 0.0)
		var pm := fl.process_material as ParticleProcessMaterial
		var grad := Gradient.new()
		grad.set_color(0, Color(0.6, 0.85, 4.0, 1.0))
		grad.set_color(1, Color(4.0, 0.9, 0.1, 0.0))
		grad.add_point(0.35, Color(4.0, 2.2, 0.4, 1.0))
		var gt := GradientTexture1D.new()
		gt.gradient = grad
		pm.color_ramp = gt
		pm.scale_min = 0.8
		pm.scale_max = 1.5
		e.add_child(fl)
		_fx_boost.append(fl)


func _make_particles(amount: int, lifetime: float, size: float, dir: Vector3, vmin: float, vmax: float, grav: float) -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.amount = amount
	p.lifetime = lifetime
	p.emitting = false
	p.local_coords = false
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var pm := ParticleProcessMaterial.new()
	pm.direction = dir.normalized()
	pm.spread = 30.0
	pm.initial_velocity_min = vmin
	pm.initial_velocity_max = vmax
	pm.gravity = Vector3(0, grav, 0)
	pm.scale_min = 0.5
	pm.scale_max = 1.0
	pm.color = Color.WHITE
	p.process_material = pm
	var quad := QuadMesh.new()
	quad.size = Vector2(size, size)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.vertex_color_use_as_albedo = true
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.albedo_texture = _soft_dot_texture()
	quad.material = m
	p.draw_pass_1 = quad
	return p


static var _dot_tex: Texture2D
static func _soft_dot_texture() -> Texture2D:
	if _dot_tex:
		return _dot_tex
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, 1))
	g.set_color(1, Color(1, 1, 1, 0))
	var gt := GradientTexture2D.new()
	gt.gradient = g
	gt.fill = GradientTexture2D.FILL_RADIAL
	gt.fill_from = Vector2(0.5, 0.5)
	gt.fill_to = Vector2(1.0, 0.5)
	gt.width = 32
	gt.height = 32
	_dot_tex = gt
	return _dot_tex


func _update_fx() -> void:
	var sparks_on := drift_dir != 0 and grounded and drift_level > 0
	for sp in _fx_sparks:
		sp.emitting = sparks_on
		if sparks_on:
			(sp.process_material as ParticleProcessMaterial).color = DRIFT_COLORS[drift_level]
	var boost_on := boost_time > 0.0
	for fl in _fx_boost:
		fl.emitting = boost_on
	var dust_on := grounded and surface == "grass" and absf(forward_speed) > 5.0
	for d in _fx_dust:
		d.emitting = dust_on
