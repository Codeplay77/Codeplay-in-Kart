extends CanvasLayer

const NAV_ACTIONS := ["ui_up", "ui_down", "ui_left", "ui_right", "ui_accept"]

var _bar: PanelContainer
var _label: Label
var _scene: Node
var _check_t := 0.0


func _ready() -> void:
	layer = 90
	process_mode = Node.PROCESS_MODE_ALWAYS
	_bar = PanelContainer.new()
	_bar.add_theme_stylebox_override("panel", UITheme.box(Color(0.03, 0.04, 0.07, 0.72), 12, 1, Color(1, 1, 1, 0.18), 10))
	_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_bar)
	_label = UITheme.label("", 18, Color(1, 1, 1, 0.9), false, 4)
	_bar.add_child(_label)
	_bar.visible = false
	InputSetup.device_changed.connect(func(_k: String) -> void: _refresh())
	get_viewport().size_changed.connect(_place_bar)


func _process(delta: float) -> void:
	_check_t -= delta
	if _check_t > 0.0:
		return
	_check_t = 0.2
	var s := get_tree().current_scene
	if s != _scene:
		_scene = s
	_refresh()


func _menu_active() -> bool:
	var s := get_tree().current_scene
	if s == null:
		return false
	if s is RaceManager:
		var r := s as RaceManager
		return get_tree().paused or r.finished_all or (r.player != null and r.player.finished)
	return true


func _refresh() -> void:
	var show := InputSetup.last_device == "pad" and _menu_active()
	_bar.visible = show
	if not show:
		return
	var s := get_tree().current_scene
	var parts: Array[String] = ["%s Selecionar" % InputSetup.pad_label("b:0")]
	# Na corrida, B só fecha a pausa (no placar e nos resultados não há "voltar").
	if not (s is RaceManager) or get_tree().paused:
		parts.append("%s Voltar" % InputSetup.pad_label("b:1"))
	if s and "nav_hints" in s:
		for h: String in s.get("nav_hints"):
			parts.append(h)
	elif _find_tabs() != null:
		parts.append("LB/RB Abas")
	_label.text = "   ".join(parts)
	_place_bar.call_deferred()


func _place_bar() -> void:
	var sz := get_viewport().get_visible_rect().size
	_bar.reset_size()
	_bar.position = Vector2(sz.x - _bar.size.x - 24.0, sz.y - _bar.size.y - 18.0)


func _input(event: InputEvent) -> void:
	if not _menu_active():
		return
	if event is InputEventJoypadButton and event.pressed and event.button_index in [JOY_BUTTON_LEFT_SHOULDER, JOY_BUTTON_RIGHT_SHOULDER]:
		var dir := -1 if event.button_index == JOY_BUTTON_LEFT_SHOULDER else 1
		var s := get_tree().current_scene
		if s and s.has_method("nav_tab"):
			s.call("nav_tab", dir)
			get_viewport().set_input_as_handled()
			return
		var tabs := _find_tabs()
		if tabs:
			tabs.current_tab = wrapi(tabs.current_tab + dir, 0, tabs.get_tab_count())
			tabs.get_tab_bar().grab_focus()
			get_viewport().set_input_as_handled()
		return
	if event is InputEventMouse or event is InputEventScreenTouch or event is InputEventScreenDrag:
		return
	var nav := false
	for a: String in NAV_ACTIONS:
		if event.is_action_pressed(a):
			nav = true
	if nav and get_viewport().gui_get_focus_owner() == null:
		var c := first_focusable(get_tree().current_scene)
		if c:
			c.grab_focus()
			get_viewport().set_input_as_handled()


func _find_tabs() -> TabContainer:
	var s := get_tree().current_scene
	if s == null:
		return null
	for t: Node in s.find_children("*", "TabContainer", true, false):
		if (t as TabContainer).is_visible_in_tree():
			return t
	return null


static func first_focusable(root: Node) -> Control:
	if root == null:
		return null
	var best: Control = null
	for n: Node in root.find_children("*", "Control", true, false):
		var c := n as Control
		if c.focus_mode == Control.FOCUS_NONE or not c.is_visible_in_tree():
			continue
		if c is BaseButton and (c as BaseButton).disabled:
			continue
		if not (c is BaseButton or c is Range or c is TabBar):
			continue
		var p := c.get_global_rect().position
		if best == null or p.y < best.get_global_rect().position.y - 4.0 or (absf(p.y - best.get_global_rect().position.y) <= 4.0 and p.x < best.get_global_rect().position.x):
			best = c
	return best
