extends Node

signal changed(section: String, key: String)

const PATH := "user://settings.cfg"

const RESOLUTIONS: Array[Vector2i] = [
	Vector2i(1280, 720), Vector2i(1366, 768), Vector2i(1600, 900), Vector2i(1920, 1080),
	Vector2i(2560, 1440), Vector2i(3840, 2160),
]
const WINDOW_MODES := ["Janela", "Tela cheia", "Tela cheia exclusiva"]
const QUALITY_NAMES := ["Baixa", "Média", "Alta", "Ultra"]
const FPS_LIMITS := [0, 30, 60, 120, 144, 240]
const CAMERA_NAMES := ["Perto", "Normal", "Longe"]
const REBINDABLE := {
	"accelerate": "Acelerar", "brake": "Frear / ré", "steer_left": "Virar à esquerda",
	"steer_right": "Virar à direita", "drift": "Drift", "use_item": "Usar item",
	"look_back": "Olhar para trás", "respawn": "Reaparecer", "pause": "Pausa",
}

var data := {
	"video": {"window_mode": 0, "resolution": 2, "vsync": true, "max_fps": 0, "render_scale": 1.0},
	"quality": {"preset": 2},
	"audio": {"master": 0.9, "music": 0.7, "sfx": 0.9, "engine": 0.75, "engine_sound": "kart"},
	"gameplay": {"camera": 1, "minimap": true, "show_fps": false, "speed_unit": "kmh", "standings": true,
		"vibration": true, "deadzone": 0.25, "touch_steer": 0, "touch_opacity": 0.55, "touch_auto_gas": true},
	"controls": {},
	"controls_pad": {},
	"meta": {"mobile_profile": 0},
}

var _fps_layer: CanvasLayer
var _fps_label: Label


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_ensure_buses()
	_load()
	_apply_mobile_defaults()
	_build_fps_overlay()
	apply_all.call_deferred()


func get_value(section: String, key: String, default: Variant = null) -> Variant:
	return data.get(section, {}).get(key, default)


func set_value(section: String, key: String, value: Variant) -> void:
	if not data.has(section):
		data[section] = {}
	data[section][key] = value
	_apply(section, key)
	save()
	changed.emit(section, key)


func save() -> void:
	var cf := ConfigFile.new()
	for section: String in data:
		for key: String in data[section]:
			cf.set_value(section, key, data[section][key])
	cf.save(PATH)


func _load() -> void:
	var cf := ConfigFile.new()
	if cf.load(PATH) != OK:
		return
	for section: String in cf.get_sections():
		if not data.has(section):
			data[section] = {}
		for key: String in cf.get_section_keys(section):
			var v: Variant = cf.get_value(section, key)
			var cur: Variant = data[section].get(key)
			if cur == null or typeof(cur) == typeof(v) or (typeof(cur) == TYPE_FLOAT and typeof(v) == TYPE_INT):
				data[section][key] = v


func is_mobile() -> bool:
	return OS.has_feature("mobile")


func _apply_mobile_defaults() -> void:
	if not is_mobile():
		return
	var version := int(data.meta.get("mobile_profile", 0))
	if version >= 2:
		return
	if version < 1:
		data.quality.preset = 0
		data.video.max_fps = 30
	# v2: escala 3D 0,6 (medido num Mali-G52: a GPU é o gargalo).
	data.video.render_scale = minf(float(data.video.render_scale), 0.6)
	data.meta.mobile_profile = 2
	save()


func view_distance() -> float:
	return 0.55 if is_mobile() else 1.0


func prop_shadows() -> bool:
	return not is_mobile()


func apply_all() -> void:
	for section: String in data:
		for key: String in data[section]:
			_apply(section, key)
	_apply_quality()
	_apply_controls()


func _apply(section: String, key: String) -> void:
	var v: Variant = data[section].get(key)
	match section:
		"video":
			_apply_video(key, v)
		"quality":
			_apply_quality()
		"audio":
			var bus: String = {"master": "Master", "music": "Music", "sfx": "SFX", "engine": "Engine"}.get(key, "")
			if bus != "":
				var idx := AudioServer.get_bus_index(bus)
				if idx >= 0:
					AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(float(v), 0.0001)))
					AudioServer.set_bus_mute(idx, float(v) <= 0.001)
		"gameplay":
			if key == "deadzone":
				_apply_controls()
			if key == "show_fps" and _fps_layer:
				_fps_layer.visible = bool(v)
		"controls", "controls_pad":
			_apply_controls()


func _apply_video(key: String, v: Variant) -> void:
	if DisplayServer.get_name() == "headless":
		return
	var root := get_tree().root
	match key:
		"window_mode":
			match int(v):
				0:
					DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
					_apply_video("resolution", data.video.resolution)
				1:
					DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
				2:
					DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN)
		"resolution":
			if int(data.video.window_mode) == 0:
				var size := RESOLUTIONS[clampi(int(v), 0, RESOLUTIONS.size() - 1)]
				var screen := DisplayServer.screen_get_usable_rect()
				size = size.min(screen.size)
				DisplayServer.window_set_size(size)
				DisplayServer.window_set_position(screen.position + (screen.size - size) / 2)
		"vsync":
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if bool(v) else DisplayServer.VSYNC_DISABLED)
		"max_fps":
			Engine.max_fps = int(v)
		"render_scale":
			var s := clampf(float(v), 0.5, 1.0)
			root.scaling_3d_scale = s
			if s >= 0.99:
				root.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
			else:
				# FSR 2 só existe no Forward+; no renderizador mobile usa FSR 1.
				root.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR if is_mobile() else Viewport.SCALING_3D_MODE_FSR2


func quality() -> int:
	return clampi(int(data.quality.preset), 0, 3)


func _apply_quality() -> void:
	var q := quality()
	var root := get_tree().root
	root.msaa_3d = [Viewport.MSAA_DISABLED, Viewport.MSAA_DISABLED, Viewport.MSAA_2X, Viewport.MSAA_4X][q]
	root.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA if q <= 2 else Viewport.SCREEN_SPACE_AA_DISABLED
	RenderingServer.directional_shadow_atlas_set_size([2048, 2048, 4096, 4096][q], true)
	RenderingServer.directional_soft_shadow_filter_set_quality([
		RenderingServer.SHADOW_QUALITY_SOFT_VERY_LOW, RenderingServer.SHADOW_QUALITY_SOFT_LOW,
		RenderingServer.SHADOW_QUALITY_SOFT_MEDIUM, RenderingServer.SHADOW_QUALITY_SOFT_HIGH][q])
	RenderingServer.environment_set_ssao_quality([
		RenderingServer.ENV_SSAO_QUALITY_VERY_LOW, RenderingServer.ENV_SSAO_QUALITY_LOW,
		RenderingServer.ENV_SSAO_QUALITY_MEDIUM, RenderingServer.ENV_SSAO_QUALITY_HIGH][q], true, 0.5, 2, 50, 300)
	if is_mobile():
		root.msaa_3d = Viewport.MSAA_DISABLED
		root.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
		RenderingServer.directional_shadow_atlas_set_size(1024 if q <= 1 else 2048, true)
		RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_HARD)


func decoration_density() -> float:
	if is_mobile():
		return [0.25, 0.4, 0.6, 0.8][quality()]
	return [0.4, 0.7, 1.0, 1.3][quality()]


func apply_environment(env: Environment) -> void:
	var q := quality()
	env.ssao_enabled = env.ssao_enabled and q >= 1
	env.glow_enabled = env.glow_enabled and q >= 1
	if is_mobile():
		env.ssao_enabled = false # (não existe no renderizador mobile)
		env.glow_enabled = env.glow_enabled and q >= 2


func apply_sun(sun: DirectionalLight3D) -> void:
	var q := quality()
	sun.directional_shadow_max_distance = [100.0, 160.0, 220.0, 300.0][q]
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS if q == 0 else DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	if is_mobile():
		sun.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
		sun.directional_shadow_max_distance = [55.0, 70.0, 90.0, 120.0][q]


func camera_distance_scale() -> float:
	return [0.82, 1.0, 1.22][clampi(int(data.gameplay.camera), 0, 2)]


func speed_text(mps: float) -> Array:
	if data.gameplay.speed_unit == "mph":
		return [int(absf(mps) * 2.237), "mph"]
	return [int(absf(mps) * 3.6), "km/h"]


func _ensure_buses() -> void:
	for bus: String in ["Music", "SFX", "Engine"]:
		if AudioServer.get_bus_index(bus) < 0:
			AudioServer.add_bus()
			var idx := AudioServer.bus_count - 1
			AudioServer.set_bus_name(idx, bus)
			AudioServer.set_bus_send(idx, "Master")
	for bus: String in ["Engine", "SFX"]:
		var idx := AudioServer.get_bus_index(bus)
		var has_compressor := false
		for i in AudioServer.get_bus_effect_count(idx):
			if AudioServer.get_bus_effect(idx, i) is AudioEffectCompressor:
				has_compressor = true
		if not has_compressor:
			var compressor := AudioEffectCompressor.new()
			compressor.threshold = -14.0 if bus == "Engine" else -10.0
			compressor.ratio = 2.0
			compressor.attack_us = 8000.0
			compressor.release_ms = 140.0
			compressor.gain = 0.0
			AudioServer.add_bus_effect(idx, compressor)
	var has_limiter := false
	for i in AudioServer.get_bus_effect_count(0):
		if AudioServer.get_bus_effect(0, i) is AudioEffectHardLimiter:
			has_limiter = true
	if not has_limiter:
		var lim := AudioEffectHardLimiter.new()
		lim.ceiling_db = -1.5
		lim.pre_gain_db = 0.0
		AudioServer.add_bus_effect(0, lim)


func key_for(action: String) -> int:
	if data.controls.has(action):
		return int(data.controls[action])
	var b: Dictionary = InputSetup.BINDINGS.get(action, {})
	return int(b.keys[0]) if b and not b.keys.is_empty() else 0


func rebind(action: String, keycode: int) -> void:
	set_value("controls", action, keycode)


func pad_for(action: String) -> String:
	if data.controls_pad.has(action):
		return str(data.controls_pad[action])
	return InputSetup.PAD_DEFAULT.get(action, "")


func rebind_pad(action: String, code: String) -> void:
	var previous := pad_for(action)
	for other: String in REBINDABLE:
		if other != action and pad_for(other) == code:
			data.controls_pad[other] = previous
	set_value("controls_pad", action, code)


func reset_controls() -> void:
	data.controls = {}
	data.controls_pad = {}
	_apply_controls()
	save()
	changed.emit("controls", "")


func _apply_controls() -> void:
	for action: String in InputSetup.BINDINGS:
		if not InputMap.has_action(action):
			continue
		for ev in InputMap.action_get_events(action):
			if ev is InputEventKey:
				InputMap.action_erase_event(action, ev)
		var keys: Array = InputSetup.BINDINGS[action].keys.duplicate()
		if data.controls.has(action):
			var custom := int(data.controls[action])
			keys.erase(custom)
			if keys.is_empty():
				keys.append(custom)
			else:
				keys[0] = custom
		for k: int in keys:
			var e := InputEventKey.new()
			e.physical_keycode = k as Key
			InputMap.action_add_event(action, e)
	var primaries := {}
	for action: String in InputSetup.BINDINGS:
		primaries[action] = pad_for(action)
	var dz := float(get_value("gameplay", "deadzone", 0.25))
	for action: String in InputSetup.BINDINGS:
		if not InputMap.has_action(action):
			continue
		InputMap.action_set_deadzone(action, dz)
		for ev in InputMap.action_get_events(action):
			if ev is InputEventJoypadButton or ev is InputEventJoypadMotion:
				InputMap.action_erase_event(action, ev)
		var codes: Array[String] = []
		if primaries[action] != "":
			codes.append(primaries[action])
		for c in InputSetup.pad_defaults(action):
			if c in codes:
				continue
			var taken := false
			for other: String in primaries:
				if other != action and primaries[other] == c:
					taken = true
			if not taken:
				codes.append(c)
		for c in codes:
			InputMap.action_add_event(action, InputSetup.pad_event(c))


func _build_fps_overlay() -> void:
	_fps_layer = CanvasLayer.new()
	_fps_layer.layer = 100
	add_child(_fps_layer)
	_fps_label = Label.new()
	_fps_label.position = Vector2(8, 4)
	_fps_label.add_theme_font_size_override("font_size", 16)
	_fps_label.add_theme_color_override("font_outline_color", Color.BLACK)
	_fps_label.add_theme_constant_override("outline_size", 4)
	_fps_layer.add_child(_fps_label)
	_fps_layer.visible = bool(data.gameplay.show_fps)


func _process(_delta: float) -> void:
	if _fps_layer.visible:
		_fps_label.text = "%d FPS" % Engine.get_frames_per_second()
