extends Node3D

const PODIUM := [ # [posição x, altura] para 1º, 2º e 3º
	[0.0, 1.2], [-2.7, 0.8], [2.7, 0.5],
]

var _result := {}


func _ready() -> void:
	if not GameState.is_career():
		GameState.goto_scene(GameState.CAREER_SCENE)
		return
	_result = GameState.finish_cup()
	var configs := {GameState.player_name(): GameState.player_config}
	for r: Dictionary in GameState.career.roster:
		configs[r.name] = r.config

	var sr := Showroom.new()
	sr.auto_rotate = false
	sr.camera_offset = Vector3(0.0, 3.4, 9.5)
	sr.look_offset = Vector3(0.0, 1.0, 0.0)
	add_child(sr)
	sr.turntable.visible = false
	for child in sr.get_children():
		if child is MeshInstance3D and (child as MeshInstance3D).mesh is TorusMesh:
			child.visible = false

	var standings: Array = _result.standings
	for i in mini(3, standings.size()):
		var x: float = PODIUM[i][0]
		var h: float = PODIUM[i][1]
		var block := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(2.5, h, 2.4)
		var m := StandardMaterial3D.new()
		m.albedo_color = [Color("#ffd23f"), Color("#c9d3de"), Color("#d8894a")][i]
		m.metallic = 0.6
		m.roughness = 0.3
		bm.material = m
		block.mesh = bm
		block.position = Vector3(x, h * 0.5, 0)
		add_child(block)
		var num := Label3D.new()
		num.text = str(i + 1)
		num.font = UITheme.title_font()
		num.font_size = 200
		num.pixel_size = 0.004
		num.position = Vector3(x, h * 0.5, 1.21)
		num.modulate = Color(0.1, 0.1, 0.12)
		num.outline_size = 0
		add_child(num)
		var kv := KartVisual.new()
		add_child(kv)
		kv.build(configs.get(standings[i].name, KartCatalog.default_config()))
		kv.position = Vector3(x, h, 0.1)
		kv.rotation.y = PI + (0.35 if x < 0 else (-0.35 if x > 0 else 0.0))
		var nl := Label3D.new()
		nl.text = standings[i].name
		nl.font = UITheme.font(UITheme.FONT_BOLD)
		nl.font_size = 72
		nl.pixel_size = 0.004
		nl.outline_size = 16
		nl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		nl.position = Vector3(x, h + 2.0, 0)
		add_child(nl)
	_confetti()
	_build_ui()
	Sfx.play("cheer", 1.0, -6.0)
	if int(_result.trophy) > 0:
		Music.play_victory()
	else:
		Music.play_menu()


func _confetti() -> void:
	var p := GPUParticles3D.new()
	p.amount = 400
	p.lifetime = 5.0
	p.position = Vector3(0, 7, 0)
	p.visibility_aabb = AABB(Vector3(-10, -10, -10), Vector3(20, 20, 20))
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(7, 0.5, 3)
	pm.direction = Vector3.DOWN
	pm.initial_velocity_min = 0.5
	pm.initial_velocity_max = 2.0
	pm.gravity = Vector3(0, -1.5, 0)
	pm.angular_velocity_min = -300
	pm.angular_velocity_max = 300
	pm.scale_min = 0.6
	pm.scale_max = 1.2
	var grad := Gradient.new()
	grad.offsets = PackedFloat32Array([0.0, 0.25, 0.5, 0.75, 1.0])
	grad.colors = PackedColorArray([Color("#ff4d1f"), Color("#ffc42e"), Color("#1e7bff"), Color("#18c46a"), Color("#ff3fa4")])
	var gt := GradientTexture1D.new()
	gt.gradient = grad
	pm.color_initial_ramp = gt
	p.process_material = pm
	var quad := QuadMesh.new()
	quad.size = Vector2(0.08, 0.14)
	var m := StandardMaterial3D.new()
	m.vertex_color_use_as_albedo = true
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	quad.material = m
	p.draw_pass_1 = quad
	add_child(p)


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.get_theme()
	layer.add_child(root)
	var cup: Dictionary = _result.cup
	var place: int = _result.place
	var head := UITheme.label(cup.name.to_upper(), 48, cup.color, true, 10)
	head.position = Vector2(48, 24)
	root.add_child(head)
	var verdict := ""
	match int(_result.trophy):
		1:
			verdict = "CAMPEÃO! Troféu de ouro"
		2:
			verdict = "2º lugar — Troféu de prata"
		3:
			verdict = "3º lugar — Troféu de bronze"
		_:
			verdict = "%dº lugar — sem troféu desta vez" % place
	var vl := UITheme.label(verdict, 34, UITheme.TEXT, true, 8)
	vl.position = Vector2(52, 90)
	root.add_child(vl)

	var panel := PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	panel.position = Vector2(-420, -370)
	panel.custom_minimum_size = Vector2(380, 0)
	root.add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 4)
	panel.add_child(v)
	v.add_child(UITheme.label("CLASSIFICAÇÃO FINAL", 24, UITheme.ACCENT_2, true))
	var standings: Array = _result.standings
	for i in standings.size():
		var st: Dictionary = standings[i]
		var hb := HBoxContainer.new()
		var c := UITheme.ACCENT_2 if st.is_player else UITheme.TEXT
		var nl := UITheme.label("%d  %s" % [i + 1, st.name], 21, c)
		nl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		hb.add_child(nl)
		hb.add_child(UITheme.label("%d pts" % st.points, 21, c, true))
		v.add_child(hb)

	var bottom := VBoxContainer.new()
	bottom.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	bottom.position = Vector2(52, -210)
	bottom.add_theme_constant_override("separation", 8)
	root.add_child(bottom)
	var unlocks: Array = _result.new_unlocks
	if not unlocks.is_empty():
		var names := []
		for u: String in unlocks:
			names.append(preload("res://scripts/ui/career_menu.gd").reward_name(u))
		bottom.add_child(UITheme.label("NOVAS PEÇAS NA GARAGEM: " + ", ".join(names), 24, Color(0.5, 1.0, 0.6), true, 8))
		var idx := TrackCatalog.CUPS.find(cup)
		if idx >= 0 and idx < TrackCatalog.CUPS.size() - 1:
			bottom.add_child(UITheme.label("%s liberada!" % TrackCatalog.CUPS[idx + 1].name, 22, TrackCatalog.CUPS[idx + 1].color, true, 6))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	bottom.add_child(row)
	var cont := Button.new()
	cont.text = "Continuar"
	cont.custom_minimum_size = Vector2(240, 58)
	cont.pressed.connect(func() -> void:
		GameState.leave_career()
		GameState.goto_scene(GameState.CAREER_SCENE))
	row.add_child(cont)
	if not unlocks.is_empty():
		var gar := Button.new()
		gar.text = "Ir para a garagem"
		gar.custom_minimum_size = Vector2(280, 58)
		gar.pressed.connect(func() -> void:
			GameState.leave_career()
			GameState.goto_scene("res://scenes/ui/garage.tscn"))
		row.add_child(gar)
	cont.grab_focus.call_deferred()
