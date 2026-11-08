extends CanvasLayer

var race: RaceManager

var _root: Control
var _place: Label
var _place_total: Label
var _lap: Label
var _time: Label
var _best: Label
var _speed: Label
var _speed_unit: Label
var _track_title: Label
var _drift_bar: ProgressBar
var _boost_bar: ProgressBar
var _item_icon: ItemIcon
var _message: Label
var _standings: VBoxContainer
var _minimap: Minimap
var _pause: Control
var _results: Control
var _help: Label
var _sp_box: Control
var _touch: TouchControls
var _live: Control
var _live_grid: GridContainer
var _live_t := 0.0
var _msg_tween: Tween
var _best_lap := INF


func _ready() -> void:
	layer = 10
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.theme = UITheme.get_theme()
	add_child(_root)
	_build()
	race.countdown_tick.connect(_on_countdown)
	race.lap_started.connect(_on_lap)
	race.race_finished.connect(_on_finished)
	race.player_finished.connect(_on_player_finished)
	race.player.item_changed.connect(func(_k: Kart, item: String) -> void: _item_icon.set_item(item))
	race.player.drift_level_changed.connect(_on_drift_level)
	race.player.got_hit.connect(func(_k: Kart) -> void: _flash("OPA!", Color(1, 0.4, 0.3)))


func _build() -> void:
	var pos_box := HBoxContainer.new()
	pos_box.position = Vector2(36, 18)
	pos_box.add_theme_constant_override("separation", 4)
	_root.add_child(pos_box)
	_place = UITheme.label("8º", 96, UITheme.ACCENT_2, true, 14)
	pos_box.add_child(_place)
	_place_total = UITheme.label("/8", 40, UITheme.TEXT, true, 10)
	_place_total.size_flags_vertical = Control.SIZE_SHRINK_END
	pos_box.add_child(_place_total)

	_standings = VBoxContainer.new()
	_standings.position = Vector2(40, 150)
	_standings.add_theme_constant_override("separation", 2)
	_root.add_child(_standings)

	var right := VBoxContainer.new()
	right.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	right.position = Vector2(-330, 22)
	right.custom_minimum_size = Vector2(300, 0)
	right.alignment = BoxContainer.ALIGNMENT_BEGIN
	_root.add_child(right)
	_lap = UITheme.label("VOLTA 1/3", 44, UITheme.TEXT, true, 10)
	_lap.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	right.add_child(_lap)
	_time = UITheme.label("00:00.00", 34, UITheme.TEXT, false, 8)
	_time.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	right.add_child(_time)
	_best = UITheme.label("", 22, UITheme.MUTED, false, 6)
	_best.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	right.add_child(_best)

	var item_panel := PanelContainer.new()
	item_panel.set_anchors_preset(Control.PRESET_CENTER_TOP)
	item_panel.position = Vector2(-60, 18)
	item_panel.custom_minimum_size = Vector2(120, 120)
	item_panel.add_theme_stylebox_override("panel", UITheme.box(Color(0.05, 0.06, 0.09, 0.7), 22, 3, Color(1, 1, 1, 0.25), 8))
	_root.add_child(item_panel)
	_item_icon = ItemIcon.new()
	_item_icon.custom_minimum_size = Vector2(100, 100)
	item_panel.add_child(_item_icon)
	item_panel.tooltip_text = "Seu item equipado"

	var sp_box := VBoxContainer.new()
	_sp_box = sp_box
	sp_box.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	sp_box.position = Vector2(-330, -190)
	sp_box.custom_minimum_size = Vector2(290, 0)
	_root.add_child(sp_box)
	var sp_row := HBoxContainer.new()
	sp_row.alignment = BoxContainer.ALIGNMENT_END
	sp_box.add_child(sp_row)
	_speed = UITheme.label("0", 84, UITheme.TEXT, true, 12)
	sp_row.add_child(_speed)
	var kmh := UITheme.label("km/h", 26, UITheme.MUTED, false, 6)
	_speed_unit = kmh
	kmh.size_flags_vertical = Control.SIZE_SHRINK_END
	sp_row.add_child(kmh)
	var drift_lbl := UITheme.label("DRIFT", 18, UITheme.MUTED, false, 4)
	drift_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	sp_box.add_child(drift_lbl)
	_drift_bar = ProgressBar.new()
	_drift_bar.custom_minimum_size = Vector2(290, 14)
	_drift_bar.max_value = Kart.DRIFT_LEVELS[2]
	_drift_bar.show_percentage = false
	sp_box.add_child(_drift_bar)
	_boost_bar = ProgressBar.new()
	_boost_bar.custom_minimum_size = Vector2(290, 8)
	_boost_bar.max_value = 1.8
	_boost_bar.show_percentage = false
	var bfill := UITheme.box(Color(0.3, 0.8, 1.0), 4, 0, Color.TRANSPARENT, 0)
	_boost_bar.add_theme_stylebox_override("fill", bfill)
	sp_box.add_child(_boost_bar)

	_minimap = Minimap.new()
	_minimap.race = race
	_minimap.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_minimap.position = Vector2(28, -300)
	_minimap.size = Vector2(270, 270)
	_root.add_child(_minimap)
	_minimap.visible = bool(Settings.get_value("gameplay", "minimap", true))
	_standings.visible = bool(Settings.get_value("gameplay", "standings", true))

	_track_title = UITheme.label("", 52, UITheme.TEXT, true, 12)
	_track_title.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_track_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_track_title.custom_minimum_size = Vector2(1200, 0)
	_track_title.position = Vector2(-600, -230)
	_root.add_child(_track_title)
	var def := TrackCatalog.get_def(race.track_id)
	var sub := ""
	if GameState.is_career():
		var cup := TrackCatalog.get_cup(GameState.career.cup)
		sub = "%s · Corrida %d/%d · %s" % [cup.name, GameState.career.race + 1, cup.tracks.size(), GameState.current_class().name]
	else:
		sub = "%s · %d volta%s" % [GameState.current_class().name, race.laps, "s" if race.laps > 1 else ""]
	_track_title.text = "%s
%s" % [def.name, sub]
	_track_title.label_settings.line_spacing = -6

	_message = UITheme.label("", 120, UITheme.ACCENT_2, true, 18)
	_message.set_anchors_preset(Control.PRESET_CENTER)
	_message.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_message.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_message.custom_minimum_size = Vector2(1200, 200)
	_message.position = Vector2(-600, -260)
	_message.pivot_offset = Vector2(600, 100)
	_root.add_child(_message)

	_help = UITheme.label("", 16, Color(1, 1, 1, 0.6), false, 4)
	_help.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_help.position = Vector2(-600, -34)
	_help.custom_minimum_size = Vector2(1200, 0)
	_help.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_root.add_child(_help)
	_update_help(InputSetup.last_device)
	InputSetup.device_changed.connect(_update_help)

	_touch = TouchControls.new()
	_root.add_child(_touch)
	_touch.visible = TouchControls.should_show()
	_layout_for_touch(_touch.visible)

	_build_pause()


func _process(_delta: float) -> void:
	if race == null or race.player == null:
		return
	var p := race.player
	var n := race.karts.size()
	_place.text = "%dº" % p.place
	_place_total.text = "/%d" % n
	_lap.text = "VOLTA %d/%d" % [clampi(p.lap + 1, 1, race.laps), race.laps]
	_time.text = UITheme.format_time(race.race_time if race.started else 0.0)
	if p.finished:
		_time.text = UITheme.format_time(p.finish_time)
	var sp: Array = Settings.speed_text(p.forward_speed)
	_speed.text = "%d" % sp[0]
	_speed_unit.text = sp[1]
	_drift_bar.value = p.drift_charge if p.drift_dir != 0 else 0.0
	_boost_bar.value = maxf(p.boost_time, 0.0)
	_minimap.queue_redraw()
	_update_standings()
	if _live and _live.visible:
		_live_t -= _delta
		if _live_t <= 0.0:
			_live_t = 0.2
			_refresh_live()
	if race.started and not p.finished and race.is_wrong_way():
		if _message.text != "CONTRA-MÃO!":
			_flash("CONTRA-MÃO!", Color(1, 0.3, 0.2), 1.2)
	if _pause.visible and Input.is_action_just_pressed("ui_cancel"):
		_toggle_pause()
	elif Input.is_action_just_pressed("pause") and race.started and _results == null and _live == null:
		_toggle_pause()


func _layout_for_touch(on: bool) -> void:
	if on:
		_sp_box.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
		_sp_box.position = Vector2(-145, -150)
		_minimap.set_anchors_preset(Control.PRESET_TOP_RIGHT)
		_minimap.position = Vector2(-230, 150)
		_minimap.size = Vector2(200, 200)
	else:
		_sp_box.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
		_sp_box.position = Vector2(-330, -190)
		_minimap.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
		_minimap.position = Vector2(28, -300)
		_minimap.size = Vector2(270, 270)


func _update_help(kind: String) -> void:
	if _touch:
		_touch.visible = TouchControls.should_show()
		_layout_for_touch(_touch.visible)
	if kind == "touch":
		_help.visible = false
		return
	_help.visible = true
	var p := func(a: String) -> String: return InputSetup.prompt(a)
	var steer := "Analógico E" if kind == "pad" else "%s/%s" % [p.call("steer_left"), p.call("steer_right")]
	_help.text = "%s acelerar · %s frear · %s virar · %s drift · %s item · %s olhar atrás · %s reaparecer · %s pausa" % [
		p.call("accelerate"), p.call("brake"), steer, p.call("drift"), p.call("use_item"),
		p.call("look_back"), p.call("respawn"), p.call("pause")]


func _update_standings() -> void:
	var order := race.karts.duplicate()
	order.sort_custom(func(a: Kart, b: Kart) -> bool: return a.place < b.place)
	while _standings.get_child_count() < order.size():
		_standings.add_child(UITheme.label("", 18, UITheme.TEXT, false, 5))
	for i in order.size():
		var k: Kart = order[i]
		var l: Label = _standings.get_child(i)
		l.text = "%d  %s" % [k.place, k.driver_name]
		l.label_settings.font_color = UITheme.ACCENT_2 if k == race.player else Color(1, 1, 1, 0.8)


func _on_countdown(v: int) -> void:
	if v == 0 and _track_title.text != "":
		var tw := create_tween()
		tw.tween_property(_track_title, "modulate:a", 0.0, 0.6)
	if v > 0:
		_flash(str(v), UITheme.TEXT, 0.9)
	else:
		_flash("VAI!", Color(0.4, 1.0, 0.4), 0.9)


func _on_lap(k: Kart, lap: int) -> void:
	if k != race.player:
		return
	if not k.lap_times.is_empty():
		_best_lap = minf(_best_lap, k.lap_times[-1])
		_best.text = "MELHOR VOLTA %s" % UITheme.format_time(_best_lap)
	if lap == race.laps:
		_flash("VOLTA FINAL!", UITheme.ACCENT_2, 1.6)
	elif lap > 1:
		_flash("VOLTA %d" % lap, UITheme.TEXT, 1.2)


func _on_drift_level(_k: Kart, level: int) -> void:
	var fill := _drift_bar.get_theme_stylebox("fill").duplicate() as StyleBoxFlat
	var colors := [UITheme.ACCENT_2, Color(0.3, 0.65, 1.0), Color(1.0, 0.55, 0.1), Color(0.75, 0.3, 1.0)]
	fill.bg_color = colors[level]
	_drift_bar.add_theme_stylebox_override("fill", fill)


func _flash(text: String, color: Color, duration := 1.0) -> void:
	_message.text = text
	_message.label_settings.font_color = color
	if _msg_tween:
		_msg_tween.kill()
	_message.scale = Vector2.ONE * 1.6
	_message.modulate.a = 1.0
	_msg_tween = create_tween()
	_msg_tween.tween_property(_message, "scale", Vector2.ONE, 0.18).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_msg_tween.tween_interval(duration)
	_msg_tween.tween_property(_message, "modulate:a", 0.0, 0.25)
	_msg_tween.tween_callback(func() -> void: _message.text = "")


func _build_pause() -> void:
	_pause = ColorRect.new()
	(_pause as ColorRect).color = Color(0, 0, 0, 0.55)
	_pause.set_anchors_preset(Control.PRESET_FULL_RECT)
	_pause.visible = false
	_root.add_child(_pause)
	var box := VBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_CENTER)
	box.position = Vector2(-170, -160)
	box.custom_minimum_size = Vector2(340, 0)
	box.add_theme_constant_override("separation", 12)
	_pause.add_child(box)
	var t := UITheme.label("PAUSA", 64, UITheme.ACCENT_2, true, 10)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(t)
	var quit_label := "Abandonar copa" if GameState.is_career() else "Menu principal"
	for pair: Array in [["Continuar", _toggle_pause], ["Reiniciar corrida", race.restart], [quit_label, race.to_menu]]:
		var b := Button.new()
		b.text = pair[0]
		UITheme.decorate_button(b, "race" if pair[0] == "Continuar" else "back", pair[0] == "Continuar")
		b.pressed.connect(pair[1])
		box.add_child(b)


func _toggle_pause() -> void:
	_pause.visible = not _pause.visible
	get_tree().paused = _pause.visible
	if _pause.visible:
		(_pause.get_child(0).get_child(1) as Button).grab_focus()


func _on_player_finished(k: Kart) -> void:
	_flash("FIM DE PROVA!", UITheme.ACCENT_2, 1.1)
	_live = ColorRect.new()
	(_live as ColorRect).color = Color(0, 0, 0, 0.35)
	_live.set_anchors_preset(Control.PRESET_FULL_RECT)
	_live.visible = false
	_root.add_child(_live)
	var panel := PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.position = Vector2(-380, -340)
	panel.custom_minimum_size = Vector2(760, 0)
	_live.add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	panel.add_child(v)
	var title := UITheme.label("FIM DE PROVA!", 56, UITheme.ACCENT_2, true, 8)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(title)
	var place := 1 + race.karts.filter(func(o: Kart) -> bool: return o != k and o.finished and o.finish_time <= k.finish_time).size()
	var sub := UITheme.label("Você chegou em %dº  ·  %s" % [place, UITheme.format_time(k.finish_time)], 26, UITheme.TEXT, true, 6)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(sub)
	_live_grid = GridContainer.new()
	_live_grid.columns = 3
	_live_grid.add_theme_constant_override("h_separation", 26)
	v.add_child(_live_grid)
	var wait := UITheme.label("Aguardando os outros pilotos cruzarem a linha…", 18, UITheme.MUTED)
	wait.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(wait)
	var buttons := HBoxContainer.new()
	buttons.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_child(buttons)
	var skip := Button.new()
	skip.text = "Pular"
	skip.pressed.connect(race.finish_now)
	buttons.add_child(skip)
	_refresh_live()
	await get_tree().create_timer(1.0).timeout
	if is_instance_valid(_live) and _results == null:
		_live.visible = true
		skip.grab_focus()


func _refresh_live() -> void:
	var order := race.karts.duplicate()
	order.sort_custom(func(a: Kart, b: Kart) -> bool: return a.place < b.place)
	for c in _live_grid.get_children():
		c.queue_free()
	for h: String in ["#", "Piloto", "Tempo"]:
		_live_grid.add_child(UITheme.label(h, 18, UITheme.MUTED))
	for k: Kart in order:
		var c := UITheme.ACCENT_2 if k == race.player else (UITheme.TEXT if k.finished else UITheme.MUTED)
		_live_grid.add_child(UITheme.label("%dº" % k.place, 24, c, true))
		_live_grid.add_child(UITheme.label(k.driver_name, 24, c))
		_live_grid.add_child(UITheme.label(UITheme.format_time(k.finish_time) if k.finished else "volta %d/%d…" % [mini(k.lap + 1, race.laps), race.laps], 24, c))


func _on_finished(results: Array) -> void:
	if is_instance_valid(_live):
		_live.queue_free()
		_live = null
	var career := GameState.is_career()
	_results = ColorRect.new()
	(_results as ColorRect).color = Color(0, 0, 0, 0.5)
	_results.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(_results)
	var row := HBoxContainer.new()
	row.set_anchors_preset(Control.PRESET_CENTER)
	row.add_theme_constant_override("separation", 24)
	row.position = Vector2(-560 if career else -380, -340)
	_results.add_child(row)
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(760, 0)
	row.add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	panel.add_child(v)
	var player_place := 0
	for r: Dictionary in results:
		if r.is_player:
			player_place = r.place
	var title := UITheme.label("%dº LUGAR!" % player_place if player_place <= 3 else "RESULTADO", 56, UITheme.ACCENT_2, true, 8)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(title)
	var grid := GridContainer.new()
	grid.columns = 5 if career else 4
	grid.add_theme_constant_override("h_separation", 26)
	v.add_child(grid)
	var headers := ["#", "Piloto", "Tempo", "Melhor volta"]
	if career:
		headers.append("Pts")
	for h: String in headers:
		grid.add_child(UITheme.label(h, 18, UITheme.MUTED))
	for r: Dictionary in results:
		var c := UITheme.ACCENT_2 if r.is_player else UITheme.TEXT
		grid.add_child(UITheme.label("%dº" % r.place, 24, c, true))
		grid.add_child(UITheme.label(r.name, 24, c))
		grid.add_child(UITheme.label(UITheme.format_time(r.time), 24, c))
		grid.add_child(UITheme.label(UITheme.format_time(r.best_lap), 24, c))
		if career:
			grid.add_child(UITheme.label("+%d" % r.get("points", 0), 24, Color(0.5, 1.0, 0.6) if r.is_player else c, true))
	if career:
		var sp := PanelContainer.new()
		sp.custom_minimum_size = Vector2(340, 0)
		row.add_child(sp)
		var sv := VBoxContainer.new()
		sv.add_theme_constant_override("separation", 4)
		sp.add_child(sv)
		var cup := TrackCatalog.get_cup(GameState.career.cup)
		sv.add_child(UITheme.label(cup.name.to_upper(), 30, cup.color, true))
		sv.add_child(UITheme.label("Classificação após %d/%d" % [GameState.career.race + 1, cup.tracks.size()], 18, UITheme.MUTED))
		var standings := GameState.cup_standings()
		for i in standings.size():
			var st: Dictionary = standings[i]
			var hb := HBoxContainer.new()
			var c2 := UITheme.ACCENT_2 if st.is_player else UITheme.TEXT
			var nm := UITheme.label("%d  %s" % [i + 1, st.name], 22, c2)
			nm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			hb.add_child(nm)
			hb.add_child(UITheme.label(str(st.points), 22, c2, true))
			sv.add_child(hb)
	var buttons := HBoxContainer.new()
	buttons.alignment = BoxContainer.ALIGNMENT_CENTER
	buttons.add_theme_constant_override("separation", 16)
	v.add_child(buttons)
	var first: Button
	if career:
		var b := Button.new()
		b.text = "Resultado da copa" if GameState.is_last_cup_race() else "Próxima corrida"
		b.pressed.connect(race.continue_career)
		buttons.add_child(b)
		first = b
		var q := Button.new()
		q.text = "Abandonar copa"
		q.pressed.connect(race.to_menu)
		buttons.add_child(q)
	else:
		var b1 := Button.new()
		b1.text = "Correr de novo"
		b1.pressed.connect(race.restart)
		buttons.add_child(b1)
		first = b1
		var b2 := Button.new()
		b2.text = "Garagem"
		b2.pressed.connect(func() -> void: GameState.goto_scene("res://scenes/ui/garage.tscn"))
		buttons.add_child(b2)
		var b3 := Button.new()
		b3.text = "Menu"
		b3.pressed.connect(race.to_menu)
		buttons.add_child(b3)
	first.grab_focus()


class ItemIcon extends Control:
	var item := ""
	var _t := 0.0

	func set_item(i: String) -> void:
		item = i
		queue_redraw()

	func _process(delta: float) -> void:
		_t += delta
		if item != "":
			queue_redraw()

	func _draw() -> void:
		var shown := item
		if item == "rolling":
			shown = ["turbo", "orb", "mine"][int(_t * 12.0) % 3]
		if shown not in ["turbo", "orb", "mine"]:
			shown = "item_empty"
		var edge := minf(size.x, size.y) * 0.84
		var pulse := 1.0 + sin(_t * 3.0) * 0.035 if item != "" else 1.0
		var dimensions := Vector2.ONE * edge * pulse
		draw_texture_rect(UITheme.icon(shown), Rect2((size - dimensions) * 0.5, dimensions), false)


class Minimap extends Control:
	var race: RaceManager
	var _pts := PackedVector2Array()
	var _rect := Rect2()

	func _ready() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _to_map(p: Vector2) -> Vector2:
		var s := minf(size.x / _rect.size.x, size.y / _rect.size.y) * 0.9
		var center := _rect.get_center()
		return size * 0.5 + (p - center) * s

	func _draw() -> void:
		if race == null or race.track == null:
			return
		if _pts.is_empty():
			_pts = race.track.get_minimap_points()
			_rect = Rect2(_pts[0], Vector2.ZERO)
			for p in _pts:
				_rect = _rect.expand(p)
		var mapped := PackedVector2Array()
		for p in _pts:
			mapped.append(_to_map(p))
		mapped.append(mapped[0])
		draw_polyline(mapped, Color(0, 0, 0, 0.55), 12.0, true)
		draw_polyline(mapped, Color(1, 1, 1, 0.85), 6.0, true)
		draw_circle(mapped[0], 6.0, Color(1, 1, 1))
		for k: Kart in race.karts:
			if k == race.player:
				continue
			var p := _to_map(Vector2(k.global_position.x, k.global_position.z))
			draw_circle(p, 7.0, Color(0, 0, 0, 0.6))
			draw_circle(p, 5.5, k.config.get("color_primary", Color.RED))
		var pp := _to_map(Vector2(race.player.global_position.x, race.player.global_position.z))
		draw_circle(pp, 10.0, Color.BLACK)
		draw_circle(pp, 8.0, UITheme.ACCENT_2)
