extends Node3D

var _showroom: Showroom
var _main_box: VBoxContainer
var _setup_panel: PanelContainer
var _preview: TrackPreview
var _track_info: Label
var _track_buttons := {}
var _titles: Array[Control] = []


func _ready() -> void:
	Music.play_menu()
	GameState.leave_career()
	_showroom = Showroom.new()
	_showroom.camera_offset = Vector3(-1.6, 1.25, 4.4)
	_showroom.look_offset = Vector3(-0.9, 0.55, 0.0)
	add_child(_showroom)
	_showroom.show_config(GameState.player_config)

	var layer := CanvasLayer.new()
	add_child(layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.get_theme()
	root.mouse_filter = Control.MOUSE_FILTER_PASS
	layer.add_child(root)

	var grad := UITheme.artwork("res://assets/ui/menu_overlay.svg", Vector2.ZERO)
	grad.stretch_mode = TextureRect.STRETCH_SCALE
	grad.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(grad)

	var eyebrow := UITheme.label("KART ARCADE  /  ESCOLHA SEU CAMINHO", 17, UITheme.CYAN)
	eyebrow.position = Vector2(84, 65)
	root.add_child(eyebrow)
	var title := UITheme.label("CODEPLAY", 82, UITheme.TEXT, true, 0)
	title.position = Vector2(78, 100)
	root.add_child(title)
	var title2 := UITheme.label("IN KART", 98, UITheme.ACCENT, true, 0)
	title2.position = Vector2(78, 175)
	root.add_child(title2)
	var sub := UITheme.label("Domine o drift. Conquiste cada curva.", 22, UITheme.MUTED)
	sub.position = Vector2(84, 292)
	root.add_child(sub)
	_titles = [eyebrow, title, title2, sub]

	_main_box = VBoxContainer.new()
	_main_box.position = Vector2(84, 354)
	_main_box.custom_minimum_size = Vector2(410, 0)
	_main_box.add_theme_constant_override("separation", 10)
	root.add_child(_main_box)
	var b_career := _button("Carreira", func() -> void: GameState.goto_scene(GameState.CAREER_SCENE), "trophy", true)
	_button("Corrida rápida", _open_setup, "race")
	_button("Garagem", func() -> void: GameState.goto_scene("res://scenes/ui/garage.tscn"), "garage")
	_button("Opções", func() -> void: GameState.goto_scene("res://scenes/ui/options.tscn"), "settings")
	_button("Sair", func() -> void: get_tree().quit(), "exit")
	(func() -> void: if b_career.is_inside_tree(): b_career.grab_focus()).call_deferred()
	var stats := UITheme.label("16 PISTAS    /    4 COPAS    /    SEU KART", 16, UITheme.CYAN)
	stats.position = Vector2(86, 752)
	root.add_child(stats)
	_titles.append(stats)
	var driver := UITheme.label("PRONTO PARA O GRID\n%s" % GameState.player_name(), 21, UITheme.TEXT)
	driver.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	driver.position = Vector2(-470, -155)
	driver.custom_minimum_size.x = 380
	driver.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	root.add_child(driver)
	_titles.append(driver)

	_build_setup(root)

	var ver := UITheme.label("CODEPLAY IN KART  /  v%s" % ProjectSettings.get_setting("application/config/version"), 14, UITheme.MUTED)
	ver.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	ver.position = Vector2(84, -43)
	root.add_child(ver)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel") and _setup_panel.visible:
		_close_setup()


func _button(text: String, cb: Callable, icon_id: String, primary := false) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(410, 66)
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	UITheme.decorate_button(b, icon_id, primary)
	b.pressed.connect(cb)
	_main_box.add_child(b)
	return b


func _build_setup(root: Control) -> void:
	_setup_panel = PanelContainer.new()
	_setup_panel.position = Vector2(60, 60)
	_setup_panel.custom_minimum_size = Vector2(1260, 0)
	_setup_panel.visible = false
	root.add_child(_setup_panel)
	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 10)
	_setup_panel.add_child(outer)
	outer.add_child(UITheme.label("CORRIDA RÁPIDA", 40, UITheme.ACCENT_2, true))
	outer.add_child(UITheme.label("Escolha o circuito e prepare sua próxima largada.", 20, UITheme.MUTED))
	var cols := HBoxContainer.new()
	cols.add_theme_constant_override("separation", 22)
	outer.add_child(cols)

	var lists := GridContainer.new()
	lists.columns = 2
	lists.add_theme_constant_override("h_separation", 14)
	lists.add_theme_constant_override("v_separation", 12)
	cols.add_child(lists)
	var group := ButtonGroup.new()
	for cup: Dictionary in TrackCatalog.CUPS:
		var cv := VBoxContainer.new()
		cv.add_theme_constant_override("separation", 4)
		cv.add_child(UITheme.label(cup.name, 20, cup.color, true))
		for tid: String in cup.tracks:
			var b := Button.new()
			b.text = TrackCatalog.get_def(tid).name
			b.toggle_mode = true
			b.button_group = group
			b.custom_minimum_size = Vector2(290, 40)
			b.add_theme_font_size_override("font_size", 19)
			b.alignment = HORIZONTAL_ALIGNMENT_LEFT
			b.pressed.connect(_select_track.bind(tid))
			b.focus_entered.connect(_select_track.bind(tid))
			cv.add_child(b)
			_track_buttons[tid] = b
		lists.add_child(cv)

	var right := VBoxContainer.new()
	right.add_theme_constant_override("separation", 10)
	cols.add_child(right)
	_preview = TrackPreview.new()
	_preview.custom_minimum_size = Vector2(560, 300)
	right.add_child(_preview)
	_track_info = UITheme.label("", 20, UITheme.MUTED)
	right.add_child(_track_info)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 20)
	grid.add_theme_constant_override("v_separation", 8)
	right.add_child(grid)

	var laps := OptionButton.new()
	for n in [1, 2, 3, 4, 5]:
		laps.add_item("%d volta%s" % [n, "s" if n > 1 else ""])
	laps.select(clampi(int(GameState.race_settings.laps) - 1, 0, 4))
	laps.item_selected.connect(func(i: int) -> void: GameState.race_settings.laps = i + 1)
	_row(grid, "Voltas", laps)

	var ai := OptionButton.new()
	for n in 8:
		ai.add_item("%d" % n)
	ai.select(clampi(int(GameState.race_settings.ai_count), 0, 7))
	ai.item_selected.connect(func(i: int) -> void: GameState.race_settings.ai_count = i)
	_row(grid, "Adversários", ai)

	var cls := OptionButton.new()
	for c: Dictionary in TrackCatalog.CLASSES:
		cls.add_item(c.name)
	cls.select(clampi(int(GameState.race_settings.class), 0, 2))
	cls.item_selected.connect(func(i: int) -> void: GameState.race_settings.class = i)
	_row(grid, "Classe", cls)

	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 12)
	right.add_child(h)
	var go := Button.new()
	go.text = "LARGAR!"
	UITheme.decorate_button(go, "race", true)
	go.custom_minimum_size = Vector2(260, 60)
	go.pressed.connect(_start_race)
	h.add_child(go)
	var back := Button.new()
	back.text = "Voltar"
	UITheme.decorate_button(back, "back")
	back.custom_minimum_size = Vector2(160, 60)
	back.pressed.connect(_close_setup)
	h.add_child(back)


func _row(grid: GridContainer, text: String, ctrl: Control) -> void:
	grid.add_child(UITheme.label(text, 22, UITheme.TEXT))
	ctrl.custom_minimum_size = Vector2(240, 44)
	grid.add_child(ctrl)


func _select_track(tid: String) -> void:
	GameState.race_settings.track = tid
	_preview.set_track(tid)
	var def := TrackCatalog.get_def(tid)
	var theme_label: String = TrackThemes.THEMES[def.theme].label
	_track_info.text = "%s  ·  %s  ·  %d m" % [def.name, theme_label, int(TrackPreview.track_length(tid))]
	(_track_buttons[tid] as Button).button_pressed = true


func _open_setup() -> void:
	_main_box.visible = false
	_setup_panel.visible = true
	for t in _titles:
		t.visible = false
	var tid: String = GameState.race_settings.track
	_select_track(tid)
	(_track_buttons[tid] as Button).grab_focus()


func _close_setup() -> void:
	_setup_panel.visible = false
	_main_box.visible = true
	for t in _titles:
		t.visible = true
	(_main_box.get_child(1) as Button).grab_focus()


func _start_race() -> void:
	GameState.save_garage()
	GameState.goto_scene(GameState.RACE_SCENE)
