extends Area3D

const RESPAWN_TIME := 2.5

var _mesh: Node3D
var _active := true
var _t := 0.0
var _respawn := 0.0


func _ready() -> void:
	collision_layer = Kart.LAYER_ITEMS
	collision_mask = Kart.LAYER_KART
	monitorable = false
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(1.6, 1.8, 1.6)
	cs.shape = bs
	add_child(cs)
	_mesh = Node3D.new()
	add_child(_mesh)
	var cube := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(1.0, 1.0, 1.0)
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.35, 0.8, 1.0, 0.35)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.metallic = 0.3
	m.roughness = 0.05
	m.rim_enabled = true
	m.rim = 1.0
	m.emission_enabled = true
	m.emission = Color(0.2, 0.55, 1.0)
	m.emission_energy_multiplier = 0.6
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	bm.material = m
	cube.mesh = bm
	cube.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_mesh.add_child(cube)
	var label := Label3D.new()
	label.text = "?"
	label.font_size = 160
	label.pixel_size = 0.004
	label.outline_size = 24
	label.modulate = Color(1.0, 0.92, 0.35)
	label.outline_modulate = Color(0.6, 0.2, 0.0)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.shaded = false
	_mesh.add_child(label)
	body_entered.connect(_on_body_entered)
	_t = randf() * TAU


func _process(delta: float) -> void:
	_t += delta
	_mesh.rotation = Vector3(0.4, _t * 1.4, 0.25)
	_mesh.position.y = sin(_t * 2.0) * 0.15
	if not _active:
		_respawn -= delta
		var s := clampf(1.0 - _respawn / 0.4, 0.0, 1.0) if _respawn < 0.4 else 0.0
		_mesh.scale = Vector3.ONE * maxf(s, 0.001)
		if _respawn <= 0.0:
			_active = true
			_mesh.scale = Vector3.ONE


func _on_body_entered(body: Node3D) -> void:
	if not _active or not body is Kart:
		return
	var kart := body as Kart
	_active = false
	_respawn = RESPAWN_TIME
	_mesh.scale = Vector3.ONE * 0.001
	if kart.item == "":
		var race := get_tree().get_first_node_in_group("race_manager")
		if race and race.has_method("roll_item"):
			race.roll_item(kart)
