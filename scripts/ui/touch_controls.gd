class_name TouchControls
extends Control
## Direção: 0 = botões ◀ ▶, 1 = analógico virtual (toque em qualquer lugar da metade
## esquerda), 2 = inclinar o aparelho (acelerômetro).

const STEER_MODES := ["Botões ◀ ▶", "Analógico virtual", "Inclinar o aparelho"]
const STICK_RANGE := 110.0
const TILT_FULL := 4.5 # m/s² de inclinação para virar tudo

## [id, ação, rótulo, âncora (fração da tela), deslocamento (px), raio]
const BUTTONS := [
	["gas", "accelerate", "ACELERA", Vector2(1, 1), Vector2(-150, -165), 92.0],
	["brake", "brake", "FREIO", Vector2(1, 1), Vector2(-335, -105), 66.0],
	["drift", "drift", "DRIFT", Vector2(1, 1), Vector2(-330, -280), 74.0],
	["item", "use_item", "ITEM", Vector2(1, 1), Vector2(-150, -385), 68.0],
	["back", "look_back", "◉", Vector2(1, 1), Vector2(-320, -440), 44.0],
	["left", "steer_left", "◀", Vector2(0, 1), Vector2(125, -150), 84.0],
	["right", "steer_right", "▶", Vector2(0, 1), Vector2(320, -150), 84.0],
	["respawn", "respawn", "↺", Vector2(0.5, 0), Vector2(-120, 78), 38.0],
	["pause", "pause", "❚❚", Vector2(0.5, 0), Vector2(120, 78), 38.0],
]

var _touch_btn := {}
var _stick_touch := -1
var _stick_origin := Vector2.ZERO
var _stick_pos := Vector2.ZERO
var _steer := 0.0
var _pressed := {}


static func should_show() -> bool:
	return InputSetup.last_device == "touch"


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	process_mode = Node.PROCESS_MODE_ALWAYS
	visibility_changed.connect(_release_all)


func _mode() -> int:
	return int(Settings.get_value("gameplay", "touch_steer", 0))


func _center(b: Array) -> Vector2:
	var sz := get_viewport_rect().size
	return Vector2(sz.x * b[3].x, sz.y * b[3].y) + (b[4] as Vector2)


func _visible_button(b: Array) -> bool:
	if b[0] in ["left", "right"]:
		return _mode() == 0
	return true


func _button_at(pos: Vector2) -> String:
	for b: Array in BUTTONS:
		if _visible_button(b) and pos.distance_to(_center(b)) <= float(b[5]) * 1.15:
			return b[0]
	return ""


func _action_of(id: String) -> String:
	for b: Array in BUTTONS:
		if b[0] == id:
			return b[1]
	return ""


func _input(event: InputEvent) -> void:
	if not is_visible_in_tree():
		return
	if get_tree().paused:
		if event is InputEventScreenTouch and event.pressed and _button_at(event.position) == "pause":
			_tap_action("pause")
			get_viewport().set_input_as_handled()
		return
	if event is InputEventScreenTouch:
		var t := event as InputEventScreenTouch
		if t.pressed:
			var id := _button_at(t.position)
			if id != "":
				_touch_btn[t.index] = id
				_set_pressed(id, true)
				get_viewport().set_input_as_handled()
			elif _mode() == 1 and t.position.x < get_viewport_rect().size.x * 0.45 and _stick_touch < 0:
				_stick_touch = t.index
				_stick_origin = t.position
				_stick_pos = t.position
				get_viewport().set_input_as_handled()
		else:
			if _touch_btn.has(t.index):
				_set_pressed(_touch_btn[t.index], false)
				_touch_btn.erase(t.index)
			if t.index == _stick_touch:
				_stick_touch = -1
				_steer = 0.0
		queue_redraw()
	elif event is InputEventScreenDrag:
		var d := event as InputEventScreenDrag
		if d.index == _stick_touch:
			_stick_pos = d.position
			_steer = clampf((_stick_pos.x - _stick_origin.x) / STICK_RANGE, -1.0, 1.0)
			queue_redraw()
			get_viewport().set_input_as_handled()
		elif _touch_btn.has(d.index):
			var id := _button_at(d.position)
			if id != "" and id != _touch_btn[d.index]:
				_set_pressed(_touch_btn[d.index], false)
				_touch_btn[d.index] = id
				_set_pressed(id, true)
				queue_redraw()


func _set_pressed(id: String, on: bool) -> void:
	var action := _action_of(id)
	if action in ["pause", "respawn"]:
		if on:
			_tap_action(action)
		return
	if on:
		_pressed[id] = true
		Input.action_press(action)
	else:
		_pressed.erase(id)
		Input.action_release(action)


## Ações de toque único (o jogo usa is_action_just_pressed nelas).
func _tap_action(action: String) -> void:
	InputSetup.tap_action(action)


func _process(_delta: float) -> void:
	if not is_visible_in_tree() or get_tree().paused:
		return
	match _mode():
		1:
			_apply_steer(_steer)
		2:
			var g := Input.get_gravity()
			var s := g.x / TILT_FULL
			_apply_steer(clampf(s if absf(s) > 0.08 else 0.0, -1.0, 1.0))
	if bool(Settings.get_value("gameplay", "touch_auto_gas", true)):
		if _pressed.has("brake"):
			Input.action_release("accelerate")
		elif not _pressed.has("gas"):
			Input.action_press("accelerate")


func _apply_steer(v: float) -> void:
	if v < 0.0:
		Input.action_press("steer_left", -v)
		Input.action_release("steer_right")
	elif v > 0.0:
		Input.action_press("steer_right", v)
		Input.action_release("steer_left")
	else:
		Input.action_release("steer_left")
		Input.action_release("steer_right")


func _release_all() -> void:
	for b: Array in BUTTONS:
		if not (b[1] in ["pause", "respawn"]):
			Input.action_release(b[1])
	_pressed.clear()
	_touch_btn.clear()
	_stick_touch = -1
	_steer = 0.0


func _exit_tree() -> void:
	_release_all()


func _draw() -> void:
	var a := float(Settings.get_value("gameplay", "touch_opacity", 0.55))
	var font := UITheme.font(UITheme.FONT_BOLD)
	for b: Array in BUTTONS:
		if not _visible_button(b):
			continue
		var c := _center(b)
		var r: float = b[5]
		var on: bool = _pressed.has(b[0])
		var fill := Color(1, 1, 1, a * (0.45 if on else 0.18))
		if b[0] == "gas":
			fill = Color(0.3, 1.0, 0.45, a * (0.7 if on else 0.35))
		elif b[0] == "brake":
			fill = Color(1.0, 0.35, 0.3, a * (0.7 if on else 0.35))
		elif b[0] == "drift":
			fill = Color(1.0, 0.75, 0.2, a * (0.7 if on else 0.35))
		draw_circle(c, r, fill)
		draw_arc(c, r, 0.0, TAU, 48, Color(1, 1, 1, a), 3.0, true)
		var label: String = b[2]
		var fs := int(clampf(r * 0.42, 20.0, 34.0)) if label.length() > 2 else int(r * 0.7)
		var tw := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
		var pos := c + Vector2(-tw * 0.5, fs * 0.35)
		draw_string_outline(font, pos, label, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, 6, Color(0, 0, 0, minf(a + 0.2, 0.85)))
		draw_string(font, pos, label, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(1, 1, 1, minf(a + 0.35, 1.0)))
	if _mode() == 1:
		var base := _stick_origin if _stick_touch >= 0 else Vector2(200, get_viewport_rect().size.y - 170)
		draw_circle(base, STICK_RANGE, Color(1, 1, 1, a * 0.15))
		draw_arc(base, STICK_RANGE, 0.0, TAU, 48, Color(1, 1, 1, a * 0.8), 2.0, true)
		var knob := base + Vector2(_steer * STICK_RANGE, 0.0)
		draw_circle(knob, 44.0, Color(1, 1, 1, a * 0.6))
