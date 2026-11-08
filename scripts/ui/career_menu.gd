extends Node3D

const TROPHY_COLORS := {1: Color("#ffd23f"), 2: Color("#d9e1ea"), 3: Color("#d8894a")}

var _class_idx := 1
var _cards: Array[Control] = []
var _class_buttons: Array[Button] = []
var _root: Control
var nav_hints: Array[String] = ["LB/RB Classe"]


func _ready() -> void:
	Music.play_menu()
	GameState.leave_career()
	_class_idx = clampi(int(GameState.race_settings.class), 0, 2)
	var sr := Showroom.new()
	sr.camera_offset = Vector3(0.0, 2.6, 7.5)
	sr.look_offset = Vector3(0.0, -0.6, 0.0)
	add_child(sr)
	sr.show_config(GameState.player_config)

	var layer := CanvasLayer.new()
	add_child(layer)
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.theme = UITheme.get_theme()
	layer.add_child(_root)
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.45)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(shade)

	UITheme.page_header(_root, "CARREIRA", "Quatro copas. Uma trajetória até o topo.", "trophy")

	var cls_row := HBoxContainer.new()
	cls_row.position = Vector2(52, 118)
	cls_row.add_theme_constant_override("separation", 10)
	_root.add_child(cls_row)
	cls_row.add_child(UITheme.label("Classe:", 24, UITheme.MUTED))
	var group := ButtonGroup.new()
	for i in TrackCatalog.CLASSES.size():
		var b := Button.new()
		b.text = TrackCatalog.CLASSES[i].name
		b.toggle_mode = true
		b.button_group = group
		b.custom_minimum_size = Vector2(120, 46)
		b.button_pressed = i == _class_idx
		b.pressed.connect(_set_class.bind(i))
		cls_row.add_child(b)
		_class_buttons.append(b)
	var hint := UITheme.label("Termine no pódio para ganhar um troféu, liberar a próxima copa e desbloquear peças.", 18, UITheme.MUTED)
	hint.position = Vector2(560, 128)
	_root.add_child(hint)

	var cards_row := HBoxContainer.new()
	cards_row.position = Vector2(40, 185)
	cards_row.add_theme_constant_override("separation", 16)
	_root.add_child(cards_row)
	for i in TrackCatalog.CUPS.size():
		var card := _build_card(i)
		cards_row.add_child(card)
		_cards.append(card)

	var back := Button.new()
	back.text = "Voltar"
	UITheme.decorate_button(back, "back")
	back.custom_minimum_size = Vector2(200, 56)
	back.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	back.position = Vector2(48, -90)
	back.pressed.connect(func() -> void: GameState.goto_scene(GameState.MENU_SCENE))
	_root.add_child(back)
	(func() -> void:
		for c in _cards:
			var b := c.find_child("Play", true, false) as Button
			if b and not b.disabled:
				b.grab_focus()
				return).call_deferred()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		GameState.goto_scene(GameState.MENU_SCENE)


func nav_tab(dir: int) -> void:
	var i := wrapi(_class_idx + dir, 0, _class_buttons.size())
	_class_buttons[i].button_pressed = true
	_set_class(i)


func _set_class(i: int) -> void:
	_class_idx = i
	GameState.race_settings.class = i
	for c in _cards:
		_refresh_card(c)


func _build_card(index: int) -> Control:
	var cup: Dictionary = TrackCatalog.CUPS[index]
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(370, 600)
	card.set_meta("index", index)
	card.add_theme_stylebox_override("panel", UITheme.box(UITheme.PANEL, 14, 1, cup.color.darkened(0.3), 16))
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	card.add_child(v)
	var banner := UITheme.artwork("res://assets/ui/landscapes/%s.svg" % TrackCatalog.get_def(cup.tracks[0]).theme, Vector2(330, 64))
	v.add_child(banner)
	var head := HBoxContainer.new()
	v.add_child(head)
	var name_l := UITheme.label(cup.name.to_upper(), 28, cup.color, true)
	name_l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(name_l)
	var trophy := TrophyIcon.new()
	trophy.name = "Trophy"
	trophy.custom_minimum_size = Vector2(44, 44)
	head.add_child(trophy)

	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 6)
	v.add_child(grid)
	for tid: String in cup.tracks:
		var cell := VBoxContainer.new()
		cell.add_theme_constant_override("separation", 0)
		var pv := TrackPreview.new()
		pv.custom_minimum_size = Vector2(160, 80)
		pv.set_track(tid)
		pv.line_color = Color(1, 1, 1, 0.95)
		cell.add_child(pv)
		var tl := UITheme.label(TrackCatalog.get_def(tid).name, 15, UITheme.TEXT)
		tl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		tl.custom_minimum_size = Vector2(160, 0)
		tl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		cell.add_child(tl)
		grid.add_child(cell)

	var rewards := []
	for r: String in cup.rewards:
		rewards.append(reward_name(r))
	var rl := UITheme.label("Recompensas:\n" + "\n".join(rewards), 17, UITheme.MUTED)
	rl.custom_minimum_size = Vector2(330, 0)
	rl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(rl)
	var classes := UITheme.label("", 16, UITheme.MUTED)
	classes.name = "Classes"
	v.add_child(classes)
	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(spacer)
	var status := UITheme.label("", 16, Color(1, 0.6, 0.5))
	status.name = "Status"
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.custom_minimum_size = Vector2(330, 0)
	v.add_child(status)
	var play := Button.new()
	play.name = "Play"
	play.text = "Disputar"
	UITheme.decorate_button(play, "race", true)
	play.custom_minimum_size = Vector2(0, 54)
	play.pressed.connect(func() -> void: GameState.start_cup(cup.id, _class_idx))
	v.add_child(play)
	_refresh_card(card)
	return card


func _refresh_card(card: Control) -> void:
	var index: int = card.get_meta("index")
	var cup: Dictionary = TrackCatalog.CUPS[index]
	var unlocked := GameState.is_cup_unlocked(index)
	var t := GameState.cup_trophy(cup.id, _class_idx)
	(card.find_child("Trophy", true, false) as TrophyIcon).set_place(t)
	var parts := []
	for i in TrackCatalog.CLASSES.size():
		var tp := GameState.cup_trophy(cup.id, i)
		parts.append("%s: %s" % [TrackCatalog.CLASSES[i].name, ["—", "Ouro", "Prata", "Bronze"][tp]])
	(card.find_child("Classes", true, false) as Label).text = "   ".join(parts)
	var play := card.find_child("Play", true, false) as Button
	play.disabled = not unlocked
	play.icon = UITheme.icon("race" if unlocked else "lock")
	var status := card.find_child("Status", true, false) as Label
	if unlocked:
		status.text = ""
	else:
		status.text = "Bloqueada — ganhe um troféu na %s para liberar." % TrackCatalog.CUPS[index - 1].name
	card.modulate = Color.WHITE if unlocked else Color(0.78, 0.8, 0.85)


static func reward_name(r: String) -> String:
	var kind := r.get_slice(":", 0)
	var id := r.get_slice(":", 1)
	var label: String = {"body": "Carroceria", "wheels": "Rodas", "spoiler": "Aerofólio"}.get(kind, kind)
	var cat: Dictionary = KartCatalog.catalog(kind)
	return "%s %s" % [label, cat[id].name if cat.has(id) else id]


class TrophyIcon extends Control:
	const COLORS := {1: Color("#ffd23f"), 2: Color("#d9e1ea"), 3: Color("#d8894a")}
	var place := 0

	func set_place(p: int) -> void:
		place = p
		queue_redraw()

	func _draw() -> void:
		var col: Color = COLORS.get(place, UITheme.MUTED.darkened(0.4))
		draw_texture_rect(UITheme.icon("trophy"), Rect2(Vector2.ZERO, size), false, col)
