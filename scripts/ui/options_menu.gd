extends Node3D

var _waiting_action := ""
var _bind_buttons := {}
var _pad_buttons := {}
var _waiting_pad := false
var _wait_started := 0
var _tabs: TabContainer
const REBIND_TIMEOUT := 6.0


func _ready() -> void:
	Music.play_menu()
	var sr := Showroom.new()
	sr.camera_offset = Vector3(-1.6, 1.5, 5.8)
	sr.look_offset = Vector3(-1.25, 0.4, 0.0)
	add_child(sr)
	sr.show_config(GameState.player_config)

	var layer := CanvasLayer.new()
	add_child(layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.get_theme()
	layer.add_child(root)

	UITheme.page_header(root, "OPÇÕES", "Ajuste o jogo ao seu jeito de pilotar.", "settings")

	var panel := PanelContainer.new()
	panel.position = Vector2(40, 115)
	panel.custom_minimum_size = Vector2(820, 640)
	root.add_child(panel)
	_tabs = TabContainer.new()
	_tabs.add_theme_font_size_override("font_size", 22)
	panel.add_child(_tabs)

	_build_video()
	_build_graphics()
	_build_audio()
	_build_gameplay()
	_build_controls()

	var back := Button.new()
	back.text = "Voltar"
	UITheme.decorate_button(back, "back")
	back.custom_minimum_size = Vector2(200, 56)
	back.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	back.position = Vector2(48, -90)
	back.pressed.connect(_back)
	root.add_child(back)
	_tabs.get_tab_bar().grab_focus.call_deferred()


func _back() -> void:
	GameState.goto_scene(GameState.MENU_SCENE)


func _page(name: String) -> GridContainer:
	var margin := MarginContainer.new()
	margin.name = name
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 18)
	_tabs.add_child(margin)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 30)
	grid.add_theme_constant_override("v_separation", 14)
	margin.add_child(grid)
	return grid


func _label(grid: GridContainer, text: String) -> void:
	var l := UITheme.label(text, 22, UITheme.TEXT)
	l.custom_minimum_size = Vector2(300, 0)
	grid.add_child(l)


func _option(grid: GridContainer, text: String, items: Array, current: int, cb: Callable) -> OptionButton:
	_label(grid, text)
	var ob := OptionButton.new()
	for it in items:
		ob.add_item(str(it))
	ob.select(clampi(current, 0, items.size() - 1))
	ob.custom_minimum_size = Vector2(380, 46)
	ob.item_selected.connect(cb)
	grid.add_child(ob)
	return ob


func _check(grid: GridContainer, text: String, current: bool, cb: Callable) -> CheckButton:
	_label(grid, text)
	var cb_ := CheckButton.new()
	cb_.button_pressed = current
	cb_.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	cb_.custom_minimum_size = Vector2(76, 48)
	cb_.toggled.connect(cb)
	grid.add_child(cb_)
	return cb_


func _slider(grid: GridContainer, text: String, current: float, min_v: float, max_v: float, step: float, cb: Callable, fmt := "%d%%", mult := 100.0) -> void:
	_label(grid, text)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 12)
	var s := HSlider.new()
	s.min_value = min_v
	s.max_value = max_v
	s.step = step
	s.value = current
	s.custom_minimum_size = Vector2(300, 32)
	s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var vl := UITheme.label(fmt % (current * mult), 20, UITheme.MUTED)
	vl.custom_minimum_size = Vector2(70, 0)
	s.value_changed.connect(func(v: float) -> void:
		vl.text = fmt % (v * mult)
		cb.call(v))
	h.add_child(s)
	h.add_child(vl)
	grid.add_child(h)
	# O HSlider não desenha o estilo "focus": contorno próprio para a navegação por controle.
	var ring := Panel.new()
	ring.add_theme_stylebox_override("panel", s.get_theme_stylebox("focus"))
	ring.set_anchors_preset(Control.PRESET_FULL_RECT)
	ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ring.visible = false
	s.add_child(ring)
	s.focus_entered.connect(func() -> void: ring.visible = true)
	s.focus_exited.connect(func() -> void: ring.visible = false)


func _build_video() -> void:
	var g := _page("Vídeo")
	_option(g, "Modo de tela", Settings.WINDOW_MODES, int(Settings.get_value("video", "window_mode", 0)),
		func(i: int) -> void: Settings.set_value("video", "window_mode", i))
	var res := []
	for r: Vector2i in Settings.RESOLUTIONS:
		res.append("%d × %d" % [r.x, r.y])
	_option(g, "Resolução (janela)", res, int(Settings.get_value("video", "resolution", 2)),
		func(i: int) -> void: Settings.set_value("video", "resolution", i))
	_check(g, "Sincronização vertical (VSync)", bool(Settings.get_value("video", "vsync", true)),
		func(on: bool) -> void: Settings.set_value("video", "vsync", on))
	var fps := []
	for f: int in Settings.FPS_LIMITS:
		fps.append("Sem limite" if f == 0 else str(f))
	_option(g, "Limite de FPS", fps, Settings.FPS_LIMITS.find(int(Settings.get_value("video", "max_fps", 0))),
		func(i: int) -> void: Settings.set_value("video", "max_fps", Settings.FPS_LIMITS[i]))
	_slider(g, "Escala de renderização 3D", float(Settings.get_value("video", "render_scale", 1.0)), 0.5, 1.0, 0.05,
		func(v: float) -> void: Settings.set_value("video", "render_scale", v))


func _build_graphics() -> void:
	var g := _page("Gráficos")
	_option(g, "Qualidade gráfica", Settings.QUALITY_NAMES, Settings.quality(),
		func(i: int) -> void: Settings.set_value("quality", "preset", i))
	var info := UITheme.label("Baixa: sem MSAA/SSAO, sombras curtas, menos vegetação.\nMédia: SSAO e brilho, FXAA.\nAlta: MSAA 2x, sombras 4K (padrão).\nUltra: MSAA 4x, sombras longas e suaves, mais vegetação.\n\nMudanças de vegetação e sombras valem a partir da próxima corrida.", 18, UITheme.MUTED)
	info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	info.custom_minimum_size = Vector2(300, 0)
	g.add_child(Control.new())
	g.add_child(info)
	_check(g, "Mostrar FPS", bool(Settings.get_value("gameplay", "show_fps", false)),
		func(on: bool) -> void: Settings.set_value("gameplay", "show_fps", on))


func _build_audio() -> void:
	var g := _page("Áudio")
	_slider(g, "Volume geral", float(Settings.get_value("audio", "master", 0.9)), 0.0, 1.0, 0.05,
		func(v: float) -> void: Settings.set_value("audio", "master", v))
	_slider(g, "Música", float(Settings.get_value("audio", "music", 0.7)), 0.0, 1.0, 0.05,
		func(v: float) -> void: Settings.set_value("audio", "music", v))
	_slider(g, "Efeitos sonoros", float(Settings.get_value("audio", "sfx", 0.9)), 0.0, 1.0, 0.05,
		func(v: float) -> void:
			Settings.set_value("audio", "sfx", v)
			Sfx.play("click"))
	_slider(g, "Motor", float(Settings.get_value("audio", "engine", 0.75)), 0.0, 1.0, 0.05,
		func(v: float) -> void: Settings.set_value("audio", "engine", v))
	var ids: Array = EngineAudio.ENGINE_SETS.keys()
	var labels: Array = []
	for id: String in ids:
		labels.append(EngineAudio.ENGINE_SETS[id].label)
	_option(g, "Som do motor", labels, maxi(ids.find(str(Settings.get_value("audio", "engine_sound", EngineAudio.DEFAULT_SET))), 0),
		func(i: int) -> void: Settings.set_value("audio", "engine_sound", ids[i]))


func _build_gameplay() -> void:
	var g := _page("Jogo")
	_option(g, "Distância da câmera", Settings.CAMERA_NAMES, int(Settings.get_value("gameplay", "camera", 1)),
		func(i: int) -> void: Settings.set_value("gameplay", "camera", i))
	_option(g, "Unidade de velocidade", ["km/h", "mph"], 1 if Settings.get_value("gameplay", "speed_unit", "kmh") == "mph" else 0,
		func(i: int) -> void: Settings.set_value("gameplay", "speed_unit", "mph" if i == 1 else "kmh"))
	_check(g, "Mostrar minimapa", bool(Settings.get_value("gameplay", "minimap", true)),
		func(on: bool) -> void: Settings.set_value("gameplay", "minimap", on))
	_check(g, "Mostrar classificação ao vivo", bool(Settings.get_value("gameplay", "standings", true)),
		func(on: bool) -> void: Settings.set_value("gameplay", "standings", on))
	_check(g, "Vibração do controle", bool(Settings.get_value("gameplay", "vibration", true)),
		func(on: bool) -> void:
			Settings.set_value("gameplay", "vibration", on)
			if on:
				Input.start_joy_vibration(InputSetup.last_pad, 0.4, 0.6, 0.25))
	_slider(g, "Zona morta do analógico", float(Settings.get_value("gameplay", "deadzone", 0.25)), 0.05, 0.6, 0.05,
		func(v: float) -> void: Settings.set_value("gameplay", "deadzone", v))
	_option(g, "Direção no toque", TouchControls.STEER_MODES, int(Settings.get_value("gameplay", "touch_steer", 0)),
		func(i: int) -> void: Settings.set_value("gameplay", "touch_steer", i))
	_check(g, "Aceleração automática (toque)", bool(Settings.get_value("gameplay", "touch_auto_gas", true)),
		func(on: bool) -> void: Settings.set_value("gameplay", "touch_auto_gas", on))
	_slider(g, "Opacidade dos botões de toque", float(Settings.get_value("gameplay", "touch_opacity", 0.55)), 0.2, 1.0, 0.05,
		func(v: float) -> void: Settings.set_value("gameplay", "touch_opacity", v))
	_label(g, "Progresso da carreira")
	var reset := Button.new()
	reset.text = "Apagar progresso…"
	reset.custom_minimum_size = Vector2(380, 46)
	reset.pressed.connect(func() -> void:
		if reset.text == "Confirmar: apagar tudo?":
			GameState.progress = {"trophies": {}, "unlocked": []}
			var defaults := KartCatalog.default_config()
			for kind: String in ["body", "wheels", "spoiler"]:
				if not GameState.is_part_unlocked(kind, GameState.player_config[kind]):
					GameState.player_config[kind] = defaults[kind]
			GameState.save_garage()
			reset.text = "Progresso apagado"
		else:
			reset.text = "Confirmar: apagar tudo?")
	g.add_child(reset)


func _build_controls() -> void:
	var g := _page("Controles")
	g.columns = 3
	g.add_theme_constant_override("v_separation", 8)
	g.add_child(UITheme.label("Ação", 18, UITheme.MUTED))
	g.add_child(UITheme.label("Teclado", 18, UITheme.MUTED))
	g.add_child(UITheme.label("Controle", 18, UITheme.MUTED))
	for action: String in Settings.REBINDABLE:
		_label(g, Settings.REBINDABLE[action])
		var b := Button.new()
		b.custom_minimum_size = Vector2(260, 40)
		b.pressed.connect(_start_rebind.bind(action, false))
		g.add_child(b)
		_bind_buttons[action] = b
		var pb := Button.new()
		pb.custom_minimum_size = Vector2(260, 40)
		pb.pressed.connect(_start_rebind.bind(action, true))
		g.add_child(pb)
		_pad_buttons[action] = pb
	g.add_child(Control.new())
	var reset := Button.new()
	reset.text = "Restaurar padrão"
	reset.custom_minimum_size = Vector2(260, 44)
	reset.pressed.connect(func() -> void:
		Settings.reset_controls()
		_refresh_binds())
	g.add_child(reset)
	var hint := UITheme.label("Analógico esquerdo e direcional sempre viram o kart.", 16, UITheme.MUTED)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.custom_minimum_size = Vector2(260, 0)
	g.add_child(hint)
	_refresh_binds()


func _refresh_binds() -> void:
	for action: String in _bind_buttons:
		(_bind_buttons[action] as Button).text = OS.get_keycode_string(Settings.key_for(action))
		(_pad_buttons[action] as Button).text = InputSetup.pad_label(Settings.pad_for(action))


func _start_rebind(action: String, pad: bool) -> void:
	_waiting_action = action
	_waiting_pad = pad
	_wait_started = Time.get_ticks_msec()
	_refresh_binds()
	if pad:
		(_pad_buttons[action] as Button).text = "Aperte um botão… (%ds)" % ceili(REBIND_TIMEOUT)
	else:
		(_bind_buttons[action] as Button).text = "Pressione uma tecla… (Esc cancela)"


## Sem teclado (controle/toque) não dá para apertar Esc: a espera também é cancelada por um
## botão do controle (na coluna do teclado), por toque/clique ou depois de alguns segundos.
func _process(_delta: float) -> void:
	if _waiting_action == "":
		return
	var left := REBIND_TIMEOUT - (Time.get_ticks_msec() - _wait_started) / 1000.0
	if left <= 0.0:
		_finish_rebind()
	elif _waiting_pad:
		(_pad_buttons[_waiting_action] as Button).text = "Aperte um botão… (%ds)" % ceili(left)


func _finish_rebind() -> void:
	var b: Button = (_pad_buttons if _waiting_pad else _bind_buttons)[_waiting_action]
	_waiting_action = ""
	_refresh_binds()
	b.grab_focus()


func _input(event: InputEvent) -> void:
	if _waiting_action == "":
		if event.is_action_pressed("ui_cancel"):
			_back()
		elif event is InputEventJoypadButton and event.pressed and event.button_index in [JOY_BUTTON_LEFT_SHOULDER, JOY_BUTTON_RIGHT_SHOULDER]:
			var d := -1 if event.button_index == JOY_BUTTON_LEFT_SHOULDER else 1
			_tabs.current_tab = wrapi(_tabs.current_tab + d, 0, _tabs.get_tab_count())
			_tabs.get_tab_bar().grab_focus()
			get_viewport().set_input_as_handled()
		return
	get_viewport().set_input_as_handled()
	var settled := Time.get_ticks_msec() - _wait_started >= 250
	# Cancela ao SOLTAR o toque/clique: o botão embaixo do dedo não recebe um clique completo.
	if settled and ((event is InputEventMouseButton and not event.pressed) or (event is InputEventScreenTouch and not event.pressed)):
		_finish_rebind()
		return
	if not _waiting_pad and settled and event is InputEventJoypadButton and event.pressed:
		_finish_rebind()
		return
	if event is InputEventKey and event.pressed and not event.echo:
		var ek := event as InputEventKey
		if ek.physical_keycode == KEY_ESCAPE:
			_finish_rebind()
		elif not _waiting_pad:
			Settings.rebind(_waiting_action, ek.physical_keycode)
			_finish_rebind()
		return
	# Ignora o próprio "A" que abriu a espera.
	if not _waiting_pad or not settled:
		return
	var code := ""
	if event is InputEventJoypadButton and event.pressed:
		code = InputSetup.pad_code(event)
	elif event is InputEventJoypadMotion and absf(event.axis_value) > 0.6:
		code = InputSetup.pad_code(event)
	if code != "":
		Settings.rebind_pad(_waiting_action, code)
		_finish_rebind()
