class_name KartVisual
extends Node3D

const NOMINAL_WHEEL_RADIUS := 0.28

static var _material_cache := {}
static var _scene_cache := {}

var config: Dictionary = {}
var wheel_spins: Array[Node3D] = []
var wheel_radii: Array[float] = []
var front_pivots: Array[Node3D] = []
var rear_wheel_sockets: Array[Node3D] = []
var exhaust_sockets: Array[Node3D] = []
var steering_wheel: Node3D
var driver_head: Node3D
var _steering_rest := Basis.IDENTITY
var _head_rest := Basis.IDENTITY
var _steer_smooth := 0.0


func build(cfg: Dictionary) -> void:
	config = cfg.duplicate()
	for c in get_children():
		c.free()
	wheel_spins.clear()
	wheel_radii.clear()
	front_pivots.clear()
	rear_wheel_sockets.clear()
	exhaust_sockets.clear()
	steering_wheel = null
	driver_head = null

	var body_def: Dictionary = KartCatalog.BODIES.get(cfg.get("body", "vortex"), KartCatalog.BODIES.vortex)
	var body := _instance(body_def.scene)
	if body == null:
		body = _fallback_body()
	body.name = "Body"
	add_child(body)

	var wheel_def: Dictionary = KartCatalog.WHEELS.get(cfg.get("wheels", "classic"), KartCatalog.WHEELS.classic)
	for sname: String in ["socket_wheel_fl", "socket_wheel_fr", "socket_wheel_rl", "socket_wheel_rr"]:
		var socket := _find(body, sname)
		if socket == null:
			continue
		var is_front := sname.contains("_f")
		var is_left := sname.ends_with("l")
		var pivot := Node3D.new()
		pivot.name = "SteerPivot"
		socket.add_child(pivot)
		var spin := Node3D.new()
		spin.name = "Spin"
		pivot.add_child(spin)
		var wheel := _instance(wheel_def.scene)
		if wheel == null:
			wheel = _fallback_wheel()
		if is_left:
			wheel.rotation.y = PI
		spin.add_child(wheel)
		wheel_spins.append(spin)
		wheel_radii.append(NOMINAL_WHEEL_RADIUS * absf(socket.scale.x))
		if is_front:
			front_pivots.append(pivot)
		else:
			rear_wheel_sockets.append(socket)

	var spoiler_def: Dictionary = KartCatalog.SPOILERS.get(cfg.get("spoiler", "none"), KartCatalog.SPOILERS.none)
	var spoiler_socket := _find(body, "socket_spoiler")
	if spoiler_socket and spoiler_def.scene != "":
		var sp := _instance(spoiler_def.scene)
		if sp:
			spoiler_socket.add_child(sp)

	var driver_socket := _find(body, "socket_driver")
	if driver_socket:
		var drv := _instance(KartCatalog.DRIVER_SCENE)
		if drv == null:
			drv = _fallback_driver()
		driver_socket.add_child(drv)
		driver_head = _find(drv, "driver_head")
		if driver_head:
			_head_rest = driver_head.basis

	steering_wheel = _find(body, "steering_wheel")
	if steering_wheel:
		_steering_rest = steering_wheel.basis
	for e: String in ["socket_exhaust_l", "socket_exhaust_r"]:
		var s := _find(body, e)
		if s:
			exhaust_sockets.append(s)

	apply_colors(cfg)


func apply_colors(cfg: Dictionary) -> void:
	config.merge(cfg, true)
	for mi: MeshInstance3D in find_children("*", "MeshInstance3D", true, false):
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		if mi.mesh == null:
			continue
		for i in mi.mesh.get_surface_count():
			var base := mi.mesh.surface_get_material(i)
			if base == null:
				continue
			var mat_name := base.resource_name.to_lower()
			var slot := ""
			for key: String in KartCatalog.MATERIAL_SLOTS:
				if mat_name.begins_with(key):
					slot = KartCatalog.MATERIAL_SLOTS[key]
					break
			if slot == "" or not cfg.has(slot):
				continue
			mi.set_surface_override_material(i, _tinted(base, slot, cfg[slot]))


static func _tinted(base: Material, slot: String, color: Color) -> Material:
	var key := "%s|%s|%s" % [base.get_instance_id(), slot, color.to_html()]
	if _material_cache.has(key):
		return _material_cache[key]
	var m: Material = base.duplicate()
	if m is BaseMaterial3D:
		var bm := m as BaseMaterial3D
		bm.albedo_color = color
		if slot in ["color_primary", "color_secondary", "color_accent", "color_helmet"]:
			bm.clearcoat_enabled = true
			bm.clearcoat = 0.7
			bm.clearcoat_roughness = 0.06
			bm.roughness = minf(bm.roughness, 0.38)
	_material_cache[key] = m
	return m


## Animação por frame. speed em m/s (positivo = frente), steer -1..1.
func animate(delta: float, speed: float, steer: float) -> void:
	for i in wheel_spins.size():
		wheel_spins[i].rotation.x = wrapf(wheel_spins[i].rotation.x - speed / wheel_radii[i] * delta, -PI, PI)
	_steer_smooth = lerpf(_steer_smooth, steer, 1.0 - exp(-12.0 * delta))
	for p in front_pivots:
		p.rotation.y = -_steer_smooth * 0.42
	if steering_wheel:
		steering_wheel.basis = _steering_rest * Basis(Vector3.BACK, _steer_smooth * 1.6)
	if driver_head:
		driver_head.basis = _head_rest * Basis.from_euler(Vector3(0.0, -_steer_smooth * 0.35, -_steer_smooth * 0.12))


func get_exhaust_points() -> Array[Node3D]:
	return exhaust_sockets


func _find(root: Node, n: String) -> Node3D:
	if root.name == n:
		return root as Node3D
	return root.find_child(n, true, false) as Node3D


static func _instance(path: String) -> Node3D:
	if path == "" or not ResourceLoader.exists(path):
		return null
	var ps: PackedScene = _scene_cache.get(path)
	if ps == null:
		ps = load(path)
		_scene_cache[path] = ps
	return ps.instantiate() as Node3D if ps else null


static func _mat(name: String, color: Color, metallic := 0.0, rough := 0.5) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.resource_name = name
	m.albedo_color = color
	m.metallic = metallic
	m.roughness = rough
	return m


func _fallback_body() -> Node3D:
	var root := Node3D.new()
	var add_box := func(size: Vector3, pos: Vector3, mat: Material) -> void:
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = size
		bm.material = mat
		mi.mesh = bm
		mi.position = pos
		root.add_child(mi)
	var primary := _mat("paint_primary", Color.RED, 0.2, 0.4)
	var secondary := _mat("paint_secondary", Color.WHITE, 0.2, 0.4)
	var dark := _mat("metal_dark", Color(0.1, 0.1, 0.12), 0.6, 0.5)
	add_box.call(Vector3(0.9, 0.18, 1.9), Vector3(0, 0.22, 0), dark)
	add_box.call(Vector3(0.7, 0.3, 0.7), Vector3(0, 0.4, -0.75), primary)
	add_box.call(Vector3(1.2, 0.25, 0.6), Vector3(0, 0.38, 0.05), secondary)
	add_box.call(Vector3(0.6, 0.35, 0.5), Vector3(0, 0.45, 0.7), primary)
	var sockets := {
		"socket_wheel_fl": [Vector3(-0.58, 0.252, -0.68), 0.9],
		"socket_wheel_fr": [Vector3(0.58, 0.252, -0.68), 0.9],
		"socket_wheel_rl": [Vector3(-0.6, 0.294, 0.68), 1.05],
		"socket_wheel_rr": [Vector3(0.6, 0.294, 0.68), 1.05],
		"socket_spoiler": [Vector3(0, 0.6, 0.85), 1.0],
		"socket_driver": [Vector3(0, 0.32, 0.25), 1.0],
		"socket_exhaust_l": [Vector3(-0.2, 0.45, 0.98), 1.0],
		"socket_exhaust_r": [Vector3(0.2, 0.45, 0.98), 1.0],
	}
	for sname: String in sockets:
		var s := Node3D.new()
		s.name = sname
		s.position = sockets[sname][0]
		s.scale = Vector3.ONE * float(sockets[sname][1])
		root.add_child(s)
	var sw := MeshInstance3D.new()
	sw.name = "steering_wheel"
	var tm := TorusMesh.new()
	tm.inner_radius = 0.1
	tm.outer_radius = 0.13
	tm.material = dark
	sw.mesh = tm
	sw.position = Vector3(0, 0.56, -0.17)
	sw.rotation.x = deg_to_rad(60)
	root.add_child(sw)
	return root


func _fallback_wheel() -> Node3D:
	var mi := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = NOMINAL_WHEEL_RADIUS
	cm.bottom_radius = NOMINAL_WHEEL_RADIUS
	cm.height = 0.24
	cm.material = _mat("rubber", Color(0.05, 0.05, 0.05), 0.0, 0.9)
	mi.mesh = cm
	mi.rotation.z = PI / 2
	var hub := MeshInstance3D.new()
	var hm := CylinderMesh.new()
	hm.top_radius = 0.16
	hm.bottom_radius = 0.16
	hm.height = 0.25
	hm.material = _mat("rim", Color.GRAY, 0.9, 0.3)
	hub.mesh = hm
	mi.add_child(hub)
	var root := Node3D.new()
	root.add_child(mi)
	return root


func _fallback_driver() -> Node3D:
	var root := Node3D.new()
	var torso := MeshInstance3D.new()
	var cap := CapsuleMesh.new()
	cap.radius = 0.2
	cap.height = 0.65
	cap.material = _mat("suit", Color.BLUE)
	torso.mesh = cap
	torso.position = Vector3(0, 0.3, 0)
	root.add_child(torso)
	var head := MeshInstance3D.new()
	head.name = "driver_head"
	var sm := SphereMesh.new()
	sm.radius = 0.19
	sm.height = 0.38
	sm.material = _mat("helmet", Color.WHITE, 0.1, 0.3)
	head.mesh = sm
	head.position = Vector3(0, 0.78, 0)
	root.add_child(head)
	return root
