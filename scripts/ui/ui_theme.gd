class_name UITheme
extends RefCounted

const ACCENT := Color("#ff7946")
const ACCENT_2 := Color("#ffd18a")
const CYAN := Color("#78dbe4")
const PANEL := Color(0.045, 0.075, 0.13, 0.96)
const TEXT := Color("#edf4ff")
const MUTED := Color("#a5b6ce")

const FONT_TITLE := "res://assets/fonts/Athabasca-ExtraBold.otf"
const FONT_BOLD := "res://assets/fonts/Athabasca-Condensed-Bold.otf"
const FONT_REGULAR := "res://assets/fonts/Athabasca-Condensed-Book.otf"

static var _theme: Theme
static var _icons := {}


static func icon(id: String) -> Texture2D:
	if not _icons.has(id):
		_icons[id] = load("res://assets/ui/icons/%s.svg" % id)
	return _icons[id]


static func decorate_button(button: Button, id: String, primary := false) -> void:
	button.icon = icon(id)
	button.expand_icon = true
	button.add_theme_constant_override("icon_max_width", 26)
	button.add_theme_constant_override("h_separation", 14)
	if primary:
		button.add_theme_stylebox_override("normal", box(Color("#c54b27"), 10, 1, ACCENT, 20))
		button.add_theme_stylebox_override("hover", box(Color("#e76536"), 10, 1, ACCENT_2, 20))
		button.add_theme_stylebox_override("pressed", box(Color("#9e381f"), 10, 1, ACCENT_2, 20))


static func artwork(path: String, dimensions: Vector2) -> TextureRect:
	var rect := TextureRect.new()
	rect.texture = load(path)
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	rect.custom_minimum_size = dimensions
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return rect


static func page_header(root: Control, text: String, subtitle: String, id: String) -> void:
	var mark := artwork("res://assets/ui/icons/%s.svg" % id, Vector2(40, 40))
	mark.position = Vector2(48, 37)
	mark.modulate = ACCENT
	root.add_child(mark)
	var title := label(text, 44, TEXT, true)
	title.position = Vector2(104, 22)
	root.add_child(title)
	var caption := label(subtitle, 18, MUTED)
	caption.position = Vector2(107, 76)
	root.add_child(caption)


static func font(path: String) -> Font:
	if ResourceLoader.exists(path):
		return load(path)
	return ThemeDB.fallback_font


static func title_font() -> Font:
	return font(FONT_TITLE)


static func box(color: Color, radius := 10, border := 0, border_color := Color.TRANSPARENT, pad := 12) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(radius)
	sb.set_border_width_all(border)
	sb.border_color = border_color
	sb.content_margin_left = pad
	sb.content_margin_right = pad
	sb.content_margin_top = pad * 0.6
	sb.content_margin_bottom = pad * 0.6
	sb.anti_aliasing = true
	return sb


static func get_theme() -> Theme:
	if _theme:
		return _theme
	var t := Theme.new()
	t.default_font = font(FONT_BOLD)
	t.default_font_size = 22
	t.set_color("font_color", "Label", TEXT)
	t.set_color("font_outline_color", "Label", Color(0, 0, 0, 0.8))

	var normal := box(Color("#17263c"), 10, 1, Color("#34465f"), 18)
	var hover := box(Color("#293d56"), 10, 1, CYAN, 18)
	var pressed := box(Color("#6c382c"), 10, 2, ACCENT, 18)
	var disabled := box(Color(0.1, 0.1, 0.12, 0.6), 12, 0, Color.TRANSPARENT, 18)
	for type: String in ["Button", "OptionButton"]:
		t.set_stylebox("normal", type, normal)
		t.set_stylebox("hover", type, hover)
		t.set_stylebox("pressed", type, pressed)
		t.set_stylebox("focus", type, box(Color(0, 0, 0, 0), 12, 3, ACCENT_2, 18))
		t.set_stylebox("disabled", type, disabled)
		t.set_color("font_color", type, TEXT)
		t.set_color("font_hover_color", type, Color.WHITE)
		t.set_color("font_pressed_color", type, Color.WHITE)
		t.set_color("font_focus_color", type, Color.WHITE)
		t.set_font_size("font_size", type, 24)
		t.set_color("font_disabled_color", type, Color("#8091aa"))
		t.set_stylebox("hover_pressed", type, pressed)
	t.set_stylebox("panel", "PanelContainer", box(PANEL, 16, 1, Color(1, 1, 1, 0.07), 20))
	t.set_stylebox("panel", "Panel", box(PANEL, 16, 1, Color(1, 1, 1, 0.07), 20))
	var bg := box(Color(1, 1, 1, 0.1), 6, 0, Color.TRANSPARENT, 0)
	var fill := box(ACCENT_2, 6, 0, Color.TRANSPARENT, 0)
	t.set_stylebox("background", "ProgressBar", bg)
	t.set_stylebox("fill", "ProgressBar", fill)
	t.set_font_size("font_size", "ProgressBar", 1)
	t.set_color("font_color", "ProgressBar", Color.TRANSPARENT)
	t.set_stylebox("panel", "PopupMenu", box(Color(0.08, 0.09, 0.12, 0.98), 8, 1, Color(1, 1, 1, 0.1), 8))
	t.set_stylebox("hover", "PopupMenu", box(ACCENT, 6, 0, Color.TRANSPARENT, 6))
	t.set_font_size("font_size", "PopupMenu", 22)
	t.set_stylebox("normal", "LineEdit", normal)
	t.set_stylebox("focus", "LineEdit", box(Color.TRANSPARENT, 10, 2, CYAN, 18))
	t.set_color("font_color", "LineEdit", TEXT)
	t.set_color("caret_color", "LineEdit", ACCENT)
	t.set_color("selection_color", "LineEdit", Color("#49647c"))
	t.set_stylebox("panel", "TabContainer", box(Color("#101c30"), 10, 1, Color("#34465f"), 12))
	for type: String in ["TabContainer", "TabBar"]:
		t.set_stylebox("tab_selected", type, box(Color("#31415a"), 8, 1, CYAN, 15))
		t.set_stylebox("tab_unselected", type, box(Color("#101c30"), 8, 0, Color.TRANSPARENT, 15))
		t.set_stylebox("tab_hovered", type, hover)
		t.set_color("font_selected_color", type, TEXT)
		t.set_color("font_unselected_color", type, MUTED)
		t.set_font_size("font_size", type, 20)
	t.set_stylebox("slider", "HSlider", box(Color("#34465f"), 4, 0, Color.TRANSPARENT, 4))
	t.set_stylebox("grabber_area", "HSlider", box(ACCENT, 4, 0, Color.TRANSPARENT, 4))
	t.set_stylebox("grabber_area_highlight", "HSlider", box(ACCENT_2, 4, 0, Color.TRANSPARENT, 4))
	t.set_icon("grabber", "HSlider", icon("slider"))
	t.set_icon("grabber_highlight", "HSlider", icon("slider"))
	t.set_icon("checked", "CheckButton", icon("toggle_on"))
	t.set_icon("unchecked", "CheckButton", icon("toggle_off"))
	for state: String in ["normal", "pressed", "hover", "hover_pressed"]:
		t.set_stylebox(state, "CheckButton", box(Color.TRANSPARENT, 8, 0, Color.TRANSPARENT, 6))
	var focus_ring := box(Color(0, 0, 0, 0), 10, 3, ACCENT_2, 6)
	focus_ring.set_expand_margin_all(4.0)
	t.set_stylebox("focus", "CheckButton", focus_ring)
	t.set_stylebox("focus", "HSlider", focus_ring)
	for type: String in ["TabContainer", "TabBar"]:
		t.set_stylebox("tab_focus", type, box(Color(0, 0, 0, 0), 8, 3, ACCENT_2, 15))
	t.set_stylebox("separator", "HSeparator", box(Color("#34465f"), 0, 0, Color.TRANSPARENT, 1))
	_theme = t
	return t


static func label(text: String, size := 22, color := TEXT, title := false, outline := 0) -> Label:
	var l := Label.new()
	l.text = text
	var ls := LabelSettings.new()
	ls.font = title_font() if title else font(FONT_BOLD)
	ls.font_size = size
	ls.font_color = color
	if outline > 0:
		ls.outline_size = outline
		ls.outline_color = Color(0, 0, 0, 0.85)
	ls.shadow_size = 0 if outline > 0 else 2
	ls.shadow_color = Color(0, 0, 0, 0.45)
	ls.shadow_offset = Vector2(0, 2)
	l.label_settings = ls
	return l


static func format_time(t: float) -> String:
	if t == INF or t < 0.0:
		return "--:--.--"
	var m := int(t / 60.0)
	var s := fmod(t, 60.0)
	return "%02d:%05.2f" % [m, s]
