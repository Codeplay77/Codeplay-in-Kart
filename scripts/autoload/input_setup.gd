extends Node

const BINDINGS := {
	"accelerate": {"keys": [KEY_W, KEY_UP], "buttons": [JOY_BUTTON_A], "axes": [[JOY_AXIS_TRIGGER_RIGHT, 1.0]]},
	"brake": {"keys": [KEY_S, KEY_DOWN], "buttons": [JOY_BUTTON_B], "axes": [[JOY_AXIS_TRIGGER_LEFT, 1.0]]},
	"steer_left": {"keys": [KEY_A, KEY_LEFT], "buttons": [JOY_BUTTON_DPAD_LEFT], "axes": [[JOY_AXIS_LEFT_X, -1.0]]},
	"steer_right": {"keys": [KEY_D, KEY_RIGHT], "buttons": [JOY_BUTTON_DPAD_RIGHT], "axes": [[JOY_AXIS_LEFT_X, 1.0]]},
	"drift": {"keys": [KEY_SPACE, KEY_SHIFT], "buttons": [JOY_BUTTON_RIGHT_SHOULDER, JOY_BUTTON_LEFT_SHOULDER], "axes": []},
	"use_item": {"keys": [KEY_E, KEY_CTRL], "buttons": [JOY_BUTTON_X, JOY_BUTTON_Y], "axes": []},
	"look_back": {"keys": [KEY_Q], "buttons": [JOY_BUTTON_RIGHT_STICK], "axes": []},
	"respawn": {"keys": [KEY_R], "buttons": [JOY_BUTTON_BACK], "axes": []},
	"pause": {"keys": [KEY_ESCAPE, KEY_P], "buttons": [JOY_BUTTON_START], "axes": []},
}


## Entrada principal do controle por ação ("b:<botão>" ou "a:<eixo>:<sinal>"), remapeável.
## As demais entradas de BINDINGS continuam valendo como secundárias (ex.: analógico + direcional).
const PAD_DEFAULT := {
	"accelerate": "a:5:1", "brake": "a:4:1", "steer_left": "a:0:-1", "steer_right": "a:0:1",
	"drift": "b:10", "use_item": "b:2", "look_back": "b:8", "respawn": "b:4", "pause": "b:6",
}
const PAD_BUTTON_NAMES := {
	0: "A", 1: "B", 2: "X", 3: "Y", 4: "View", 5: "Guia", 6: "Menu", 7: "LS", 8: "RS",
	9: "LB", 10: "RB", 11: "D-pad ↑", 12: "D-pad ↓", 13: "D-pad ←", 14: "D-pad →",
	15: "Misc", 16: "Paddle 1", 17: "Paddle 2", 18: "Paddle 3", 19: "Paddle 4", 20: "Touchpad",
}
const PAD_AXIS_NAMES := {
	"0:-1": "Analógico E ←", "0:1": "Analógico E →", "1:-1": "Analógico E ↑", "1:1": "Analógico E ↓",
	"2:-1": "Analógico D ←", "2:1": "Analógico D →", "3:-1": "Analógico D ↑", "3:1": "Analógico D ↓",
	"4:1": "LT", "5:1": "RT",
}

signal device_changed(kind: String)
var last_device := "keyboard"
var last_pad := 0


func _set_device(kind: String) -> void:
	if kind != last_device:
		last_device = kind
		device_changed.emit(kind)


func _on_joy_connection(device: int, connected: bool) -> void:
	if connected:
		last_pad = device
		_set_device("pad")
	elif OS.has_feature("mobile") and Input.get_connected_joypads().is_empty():
		_set_device("touch")


func _input(event: InputEvent) -> void:
	var kind := ""
	if event is InputEventJoypadButton and event.pressed:
		kind = "pad"
		last_pad = event.device
	elif event is InputEventJoypadMotion and absf(event.axis_value) > 0.5:
		kind = "pad"
		last_pad = event.device
	elif event is InputEventKey and event.pressed:
		kind = "keyboard"
	elif event is InputEventMouseButton and event.pressed and event.device != InputEvent.DEVICE_ID_EMULATION:
		kind = "keyboard" # (o mouse emulado a partir do toque não conta)
	elif event is InputEventScreenTouch and event.pressed:
		kind = "touch"
	if kind != "":
		_set_device(kind)


## Navegação dos menus pelo controle: A confirma, B volta, direcional e analógico esquerdo
## movem o foco. (O mapa padrão desta versão do Godot não traz todos os botões do controle.)
const UI_PAD := {
	"ui_accept": [JOY_BUTTON_A], "ui_cancel": [JOY_BUTTON_B],
	"ui_up": [JOY_BUTTON_DPAD_UP], "ui_down": [JOY_BUTTON_DPAD_DOWN],
	"ui_left": [JOY_BUTTON_DPAD_LEFT], "ui_right": [JOY_BUTTON_DPAD_RIGHT],
}
const UI_AXES := {"ui_up": [JOY_AXIS_LEFT_Y, -1.0], "ui_down": [JOY_AXIS_LEFT_Y, 1.0],
	"ui_left": [JOY_AXIS_LEFT_X, -1.0], "ui_right": [JOY_AXIS_LEFT_X, 1.0]}


func _ensure_ui_pad_events() -> void:
	for action: String in UI_PAD:
		for btn: int in UI_PAD[action]:
			var ev := InputEventJoypadButton.new()
			ev.button_index = btn as JoyButton
			if not InputMap.action_has_event(action, ev):
				InputMap.action_add_event(action, ev)
	for action: String in UI_AXES:
		var ev := InputEventJoypadMotion.new()
		ev.axis = UI_AXES[action][0] as JoyAxis
		ev.axis_value = UI_AXES[action][1]
		if not InputMap.action_has_event(action, ev):
			InputMap.action_add_event(action, ev)


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_GO_BACK_REQUEST:
		var in_race := get_tree().get_first_node_in_group("race_manager") != null
		tap_action("pause" if in_race else "ui_cancel")


## Simula um toque rápido numa ação (aperta e solta alguns quadros depois, para
## is_action_just_pressed enxergar).
func tap_action(action: String) -> void:
	var ev := InputEventAction.new()
	ev.action = action
	ev.pressed = true
	Input.parse_input_event(ev)
	await get_tree().create_timer(0.06, true, false, true).timeout
	var up := InputEventAction.new()
	up.action = action
	up.pressed = false
	Input.parse_input_event(up)


static func pad_event(code: String) -> InputEvent:
	var parts := code.split(":")
	if parts[0] == "b":
		var jb := InputEventJoypadButton.new()
		jb.button_index = int(parts[1]) as JoyButton
		return jb
	var jm := InputEventJoypadMotion.new()
	jm.axis = int(parts[1]) as JoyAxis
	jm.axis_value = float(parts[2])
	return jm


static func pad_code(event: InputEvent) -> String:
	if event is InputEventJoypadButton:
		return "b:%d" % event.button_index
	if event is InputEventJoypadMotion:
		return "a:%d:%d" % [event.axis, 1 if event.axis_value > 0.0 else -1]
	return ""


static func pad_defaults(action: String) -> Array[String]:
	var out: Array[String] = []
	if PAD_DEFAULT.has(action):
		out.append(PAD_DEFAULT[action])
	var b: Dictionary = BINDINGS.get(action, {})
	for ax: Array in b.get("axes", []):
		var c := "a:%d:%d" % [ax[0], 1 if ax[1] > 0 else -1]
		if c not in out:
			out.append(c)
	for btn: int in b.get("buttons", []):
		var c := "b:%d" % btn
		if c not in out:
			out.append(c)
	return out


static func pad_label(code: String) -> String:
	var parts := code.split(":")
	if parts.size() >= 2 and parts[0] == "b":
		return PAD_BUTTON_NAMES.get(int(parts[1]), "Botão %s" % parts[1])
	if parts.size() == 3:
		return PAD_AXIS_NAMES.get("%s:%s" % [parts[1], parts[2]], "Eixo %s" % parts[1])
	return "?"


func prompt(action: String) -> String:
	if last_device == "pad":
		return pad_label(Settings.pad_for(action))
	return OS.get_keycode_string(Settings.key_for(action))


func rumble(weak: float, strong: float, duration: float) -> void:
	if last_device != "pad" or not bool(Settings.get_value("gameplay", "vibration", true)):
		return
	Input.start_joy_vibration(last_pad, clampf(weak, 0.0, 1.0), clampf(strong, 0.0, 1.0), duration)


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	if OS.has_feature("mobile"):
		var pads := Input.get_connected_joypads()
		last_device = "pad" if not pads.is_empty() else "touch"
		if not pads.is_empty():
			last_pad = pads[0]
	Input.joy_connection_changed.connect(_on_joy_connection)
	_ensure_ui_pad_events()
	for action: String in BINDINGS:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.25)
		var b: Dictionary = BINDINGS[action]
		for k: int in b.keys:
			var ev := InputEventKey.new()
			ev.physical_keycode = k as Key
			InputMap.action_add_event(action, ev)
		for btn: int in b.buttons:
			var jb := InputEventJoypadButton.new()
			jb.button_index = btn as JoyButton
			InputMap.action_add_event(action, jb)
		for ax: Array in b.axes:
			var jm := InputEventJoypadMotion.new()
			jm.axis = ax[0] as JoyAxis
			jm.axis_value = ax[1]
			InputMap.action_add_event(action, jm)
