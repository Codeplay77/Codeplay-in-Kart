class_name Showroom
extends Node3D

const HDRI := "res://assets/textures/sky/qwantani_late_afternoon_puresky_2k.hdr"

var kart: KartVisual
var turntable: Node3D
var camera: Camera3D
var auto_rotate := true
var spin_speed := 0.35
var camera_offset := Vector3(0.0, 1.35, 4.6)
var look_offset := Vector3(0.0, 0.45, 0.0)
var _drag := false
var _yaw := 0.6
var _yaw_vel := 0.0


func _ready() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	if ResourceLoader.exists(HDRI):
		var psm := PanoramaSkyMaterial.new()
		psm.panorama = load(HDRI)
		psm.energy_multiplier = 0.55
		sky.sky_material = psm
	else:
		sky.sky_material = ProceduralSkyMaterial.new()
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.7
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_white = 6.0
	env.glow_enabled = true
	env.glow_intensity = 0.5
	env.glow_hdr_threshold = 1.2
	env.ssao_enabled = true
	env.fog_enabled = true
	env.fog_light_color = Color(0.08, 0.06, 0.1)
	env.fog_density = 0.035
	env.fog_sky_affect = 0.85
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.1
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var key := DirectionalLight3D.new()
	key.light_color = Color(1.0, 0.9, 0.8)
	key.light_energy = 1.6
	key.shadow_enabled = true
	key.directional_shadow_max_distance = 20.0
	key.rotation_degrees = Vector3(-42, 35, 0)
	add_child(key)
	var rim := SpotLight3D.new()
	rim.light_color = Color(1.0, 0.45, 0.2)
	rim.light_energy = 7.0
	rim.spot_range = 14.0
	rim.spot_angle = 35.0
	rim.position = Vector3(-3.5, 3.0, -4.0)
	add_child(rim)
	rim.look_at(Vector3(0, 0.4, 0))
	var fill := SpotLight3D.new()
	fill.light_color = Color(0.4, 0.6, 1.0)
	fill.light_energy = 4.0
	fill.spot_range = 14.0
	fill.spot_angle = 40.0
	fill.position = Vector3(4.0, 2.5, -2.5)
	add_child(fill)
	fill.look_at(Vector3(0, 0.4, 0))

	var floor_mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(60, 60)
	var fm := StandardMaterial3D.new()
	fm.albedo_color = Color(0.05, 0.05, 0.065)
	fm.metallic = 0.4
	fm.roughness = 0.55
	pm.material = fm
	floor_mi.mesh = pm
	add_child(floor_mi)
	turntable = Node3D.new()
	add_child(turntable)
	var disc := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = 1.9
	cm.bottom_radius = 2.0
	cm.height = 0.12
	cm.radial_segments = 96
	var dm := StandardMaterial3D.new()
	dm.albedo_color = Color(0.13, 0.13, 0.16)
	dm.metallic = 0.85
	dm.roughness = 0.3
	cm.material = dm
	disc.mesh = cm
	disc.position.y = 0.06
	turntable.add_child(disc)
	var ring := MeshInstance3D.new()
	var tm := TorusMesh.new()
	tm.inner_radius = 1.98
	tm.outer_radius = 2.02
	tm.rings = 96
	var rm := StandardMaterial3D.new()
	rm.albedo_color = UITheme.ACCENT
	rm.emission_enabled = true
	rm.emission = UITheme.ACCENT
	rm.emission_energy_multiplier = 1.4
	tm.material = rm
	ring.mesh = tm
	ring.position.y = 0.1
	add_child(ring)

	kart = KartVisual.new()
	kart.position.y = 0.12
	turntable.add_child(kart)

	camera = Camera3D.new()
	camera.fov = 40.0
	add_child(camera)
	camera.current = true
	_place_camera()


func show_config(cfg: Dictionary) -> void:
	kart.build(cfg)


func _place_camera() -> void:
	camera.position = camera_offset
	camera.look_at(look_offset)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		_drag = event.pressed
	elif event is InputEventMouseMotion and _drag:
		_yaw_vel = (event as InputEventMouseMotion).relative.x * 0.01
		_yaw += _yaw_vel


func _process(delta: float) -> void:
	var rx := Input.get_joy_axis(InputSetup.last_pad, JOY_AXIS_RIGHT_X)
	if absf(rx) > 0.2:
		_yaw += rx * 2.6 * delta
		_yaw_vel = 0.0
	if not _drag:
		_yaw_vel = lerpf(_yaw_vel, 0.0, 1.0 - exp(-3.0 * delta))
		if auto_rotate:
			_yaw += spin_speed * delta + _yaw_vel
	turntable.rotation.y = _yaw
	kart.animate(delta, 0.0, sin(Time.get_ticks_msec() * 0.0008) * 0.4)
	_place_camera()
