extends Node3D

var _showroom: Showroom
var _cfg: Dictionary
var _part_labels := {}
var _stat_bars := {}
var _desc: Label
var _swatch_groups := {}
var _last_unlocked := {}
var _lock_label: Label
var _hint: Label
var nav_hints: Array[String] = ["RS Girar kart"]


func _ready() -> void:
	Music.play_menu()
	_cfg = GameState.player_config.duplicate()
	for kind: String in ["body", "wheels", "spoiler"]:
		_last_unlocked[kind] = _cfg[kind]
	_showroom = Showroom.new()
	_showroom.camera_offset = Vector3(-0.6, 1.9, 6.4)
	_showroom.look_offset = Vector3(-0.55, 0.4, 0.0)
	add_child(_showroom)
	_showroom.show_config(_cfg)

	var layer := CanvasLayer.new()
	add_child(layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.get_theme()
	root.mouse_filter = Control.MOUSE_FILTER_PASS
	layer.add_child(root)

	UITheme.page_header(root, "GARAGEM", "Seu estilo. Sua máquina. Sua próxima vitória.", "garage")

	var left := PanelContainer.new()
	left.position = Vector2(36, 115)
	left.custom_minimum_size = Vector2(560, 0)
	root.add_child(left)
	var lv := VBoxContainer.new()
	lv.add_theme_constant_override("separation", 10)
	left.add_child(lv)

	var name_row := HBoxContainer.new()
	name_row.add_child(_fixed(UITheme.label("Piloto", 22, UITheme.MUTED), 150))
	var name_edit := LineEdit.new()
	name_edit.text = str(_cfg.get("driver_name", "Você"))
	name_edit.max_length = 16
	name_edit.custom_minimum_size = Vector2(340, 44)
	name_edit.text_changed.connect(func(t: String) -> void: _cfg.driver_name = t if t.strip_edges() != "" else "Você")
	name_edit.gui_input.connect(func(e: InputEvent) -> void:
		if e is InputEventJoypadButton and e.is_action_pressed("ui_accept"):
			if name_edit.is_editing():
				name_edit.unedit()
			else:
				name_edit.edit()
			name_edit.accept_event())
	name_row.add_child(name_edit)
	lv.add_child(name_row)

	_part_selector(lv, "body", "Carroceria", KartCatalog.BODIES)
	_part_selector(lv, "wheels", "Rodas", KartCatalog.WHEELS)
	_part_selector(lv, "spoiler", "Aerofólio", KartCatalog.SPOILERS)

	lv.add_child(HSeparator.new())
	for slot: String in KartCatalog.COLOR_SLOTS:
		_color_row(lv, slot, KartCatalog.COLOR_SLOTS[slot])

	var right := PanelContainer.new()
	right.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	right.position = Vector2(-460, 115)
	right.custom_minimum_size = Vector2(420, 0)
	root.add_child(right)
	var rv := VBoxContainer.new()
	rv.add_theme_constant_override("separation", 8)
	right.add_child(rv)
	rv.add_child(UITheme.label("ATRIBUTOS", 30, UITheme.ACCENT_2, true))
	for key: String in KartCatalog.STAT_KEYS:
		var row := HBoxContainer.new()
		row.add_child(_fixed(UITheme.label(KartCatalog.STAT_LABELS[key], 20), 130))
		var bar := ProgressBar.new()
		bar.max_value = 10
		bar.min_value = 0
		bar.show_percentage = false
		bar.custom_minimum_size = Vector2(240, 18)
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		row.add_child(bar)
		rv.add_child(row)
		_stat_bars[key] = bar
	_lock_label = UITheme.label("", 18, Color(1.0, 0.65, 0.4))
	_lock_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_lock_label.custom_minimum_size = Vector2(380, 0)
	rv.add_child(_lock_label)
	_desc = UITheme.label("", 18, UITheme.MUTED)
	_desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_desc.custom_minimum_size = Vector2(380, 0)
	rv.add_child(_desc)

	var buttons := HBoxContainer.new()
	buttons.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	buttons.position = Vector2(-560, -100)
	buttons.add_theme_constant_override("separation", 14)
	root.add_child(buttons)
	var rnd := Button.new()
	rnd.text = "Aleatório"
	UITheme.decorate_button(rnd, "shuffle")
	rnd.custom_minimum_size = Vector2(170, 60)
	rnd.pressed.connect(_randomize)
	buttons.add_child(rnd)
	var save := Button.new()
	save.text = "Salvar e voltar"
	UITheme.decorate_button(save, "save", true)
	save.custom_minimum_size = Vector2(320, 60)
	save.pressed.connect(_save_and_back)
	buttons.add_child(save)
	save.grab_focus.call_deferred()

	_hint = UITheme.label("", 16, Color(1, 1, 1, 0.45))
	_hint.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_hint.position = Vector2(-160, -40)
	root.add_child(_hint)
	_set_hint(InputSetup.last_device)
	InputSetup.device_changed.connect(_set_hint)

	_refresh()


func _set_hint(kind: String) -> void:
	_hint.text = {"pad": "Analógico direito gira o kart", "touch": "Arraste na tela para girar o kart"}.get(kind, "Arraste com o mouse para girar o kart")


func _fixed(c: Control, w: float) -> Control:
	c.custom_minimum_size.x = w
	return c


func _part_selector(parent: Control, key: String, title: String, catalog: Dictionary) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	row.add_child(_fixed(UITheme.label(title, 22, UITheme.MUTED), 150))
	var prev := Button.new()
	UITheme.decorate_button(prev, "back")
	prev.tooltip_text = "Peça anterior"
	prev.custom_minimum_size = Vector2(52, 48)
	row.add_child(prev)
	var lbl := UITheme.label("", 24, UITheme.TEXT, true)
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lbl.custom_minimum_size = Vector2(230, 0)
	row.add_child(lbl)
	var next := Button.new()
	UITheme.decorate_button(next, "next")
	next.tooltip_text = "Próxima peça"
	next.custom_minimum_size = Vector2(52, 48)
	row.add_child(next)
	parent.add_child(row)
	_part_labels[key] = lbl
	var keys: Array = catalog.keys()
	var cycle := func(dir: int) -> void:
		var i := keys.find(_cfg[key])
		_cfg[key] = keys[posmod(i + dir, keys.size())]
		if GameState.is_part_unlocked(key, _cfg[key]):
			_last_unlocked[key] = _cfg[key]
		_showroom.show_config(_cfg)
		_refresh()
	prev.pressed.connect(cycle.bind(-1))
	next.pressed.connect(cycle.bind(1))


func _color_row(parent: Control, slot: String, title: String) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	row.add_child(_fixed(UITheme.label(title, 19, UITheme.MUTED), 150))
	var flow := HFlowContainer.new()
	flow.custom_minimum_size = Vector2(380, 0)
	flow.add_theme_constant_override("h_separation", 4)
	flow.add_theme_constant_override("v_separation", 4)
	row.add_child(flow)
	var group: Array[Button] = []
	for c: Color in KartCatalog.PALETTE:
		var b := Button.new()
		b.custom_minimum_size = Vector2(20, 20)
		b.focus_mode = Control.FOCUS_ALL
		var ring := UITheme.box(Color.TRANSPARENT, 7, 3, Color.WHITE, 0)
		ring.set_expand_margin_all(4.0)
		b.add_theme_stylebox_override("focus", ring)
		b.add_theme_stylebox_override("normal", UITheme.box(c, 5, 2, Color(0, 0, 0, 0.5), 0))
		b.add_theme_stylebox_override("hover", UITheme.box(c.lightened(0.15), 5, 2, Color.WHITE, 0))
		b.add_theme_stylebox_override("pressed", UITheme.box(c, 5, 3, UITheme.ACCENT_2, 0))
		b.toggle_mode = true
		b.set_meta("color", c)
		b.pressed.connect(func() -> void:
			_cfg[slot] = c
			_showroom.kart.apply_colors(_cfg)
			_refresh())
		flow.add_child(b)
		group.append(b)
	_swatch_groups[slot] = group
	parent.add_child(row)


func _refresh() -> void:
	var locks := []
	for kind: String in ["body", "wheels", "spoiler"]:
		var cat: Dictionary = KartCatalog.catalog(kind)
		var lbl: Label = _part_labels[kind]
		var unlocked := GameState.is_part_unlocked(kind, _cfg[kind])
		lbl.text = cat[_cfg[kind]].name + ("" if unlocked else " (bloq.)")
		lbl.label_settings.font_color = UITheme.TEXT if unlocked else Color(1.0, 0.6, 0.4)
		if not unlocked:
			locks.append("%s: ganhe um troféu na %s" % [cat[_cfg[kind]].name, GameState.part_unlock_cup(kind, _cfg[kind])])
	_lock_label.text = ("BLOQUEADO — " + "; ".join(locks) + ". Só peças liberadas são salvas.") if not locks.is_empty() else ""
	_desc.text = KartCatalog.BODIES[_cfg.body].desc
	var stats := KartCatalog.compute_stats(_cfg)
	for key: String in _stat_bars:
		var bar: ProgressBar = _stat_bars[key]
		create_tween().tween_property(bar, "value", float(stats[key]), 0.25)
	for slot: String in _swatch_groups:
		for b: Button in _swatch_groups[slot]:
			b.set_pressed_no_signal((b.get_meta("color") as Color).is_equal_approx(_cfg[slot]))


func _randomize() -> void:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	var name_keep: String = _cfg.driver_name
	_cfg = KartCatalog.random_config(rng)
	_cfg.driver_name = name_keep
	for kind: String in ["body", "wheels", "spoiler"]:
		var options: Array = KartCatalog.catalog(kind).keys().filter(func(k: String) -> bool: return GameState.is_part_unlocked(kind, k))
		_cfg[kind] = options[rng.randi() % options.size()]
		_last_unlocked[kind] = _cfg[kind]
	_showroom.show_config(_cfg)
	_refresh()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		_save_and_back()
		get_viewport().set_input_as_handled()


func _save_and_back() -> void:
	for kind: String in ["body", "wheels", "spoiler"]:
		if not GameState.is_part_unlocked(kind, _cfg[kind]):
			_cfg[kind] = _last_unlocked[kind]
	GameState.player_config = _cfg
	GameState.save_garage()
	GameState.goto_scene("res://scenes/ui/main_menu.tscn")
