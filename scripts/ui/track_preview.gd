class_name TrackPreview
extends Control

static var _cache := {}
static var _art_cache := {}

var track_id := ""
var line_color := Color.WHITE
var _pts := PackedVector3Array()
var _art: Texture2D


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func set_track(id: String) -> void:
	track_id = id
	_pts = points_for(id)
	var theme_id: String = TrackCatalog.get_def(id).theme
	if not _art_cache.has(theme_id):
		_art_cache[theme_id] = load("res://assets/ui/landscapes/%s.svg" % theme_id)
	_art = _art_cache[theme_id]
	queue_redraw()


static func points_for(id: String) -> PackedVector3Array:
	if _cache.has(id):
		return _cache[id]
	var ctrl := PackedVector3Array()
	var def := TrackCatalog.get_def(id)
	if def.has("scene"):
		var t := (load(def.scene) as PackedScene).instantiate() as Track
		ctrl = t._layout_points()
		t.free()
	elif TrackLayouts.LAYOUTS.has(id):
		ctrl = PackedVector3Array(TrackLayouts.LAYOUTS[id].points)
	var curve := Curve3D.new()
	var n := ctrl.size()
	for i in n + 1:
		var p0 := ctrl[(i - 1 + n) % n]
		var p2 := ctrl[(i + 1) % n]
		var tan := (p2 - p0) / 6.0
		curve.add_point(ctrl[i % n], -tan, tan)
	curve.bake_interval = 4.0
	var baked := curve.get_baked_points()
	_cache[id] = baked
	return baked


static func track_length(id: String) -> float:
	var pts := points_for(id)
	var l := 0.0
	for i in pts.size() - 1:
		l += pts[i].distance_to(pts[i + 1])
	return l


func _draw() -> void:
	if _pts.size() < 2:
		return
	var frame := UITheme.box(Color("#101c30"), 10, 1, Color("#3c536c"), 0)
	draw_style_box(frame, Rect2(Vector2.ZERO, size))
	var art_width := size.x * 0.48
	if _art:
		var destination := Rect2(Vector2(5, 5), Vector2(art_width - 5, size.y - 10))
		var texture_size := _art.get_size()
		var cover_scale := maxf(destination.size.x / texture_size.x, destination.size.y / texture_size.y)
		var source_size := destination.size / maxf(cover_scale, 0.001)
		draw_texture_rect_region(_art, destination, Rect2((texture_size - source_size) * 0.5, source_size))
	draw_line(Vector2(art_width + 5, 12), Vector2(art_width + 5, size.y - 12), Color("#34465f"), 1.0)
	var mn := Vector2(INF, INF)
	var mx := Vector2(-INF, -INF)
	var ymin := INF
	var ymax := -INF
	for p in _pts:
		mn = mn.min(Vector2(p.x, p.z))
		mx = mx.max(Vector2(p.x, p.z))
		ymin = minf(ymin, p.y)
		ymax = maxf(ymax, p.y)
	var ext := mx - mn
	var map_size := Vector2(size.x * 0.46, size.y)
	var sc := minf(map_size.x / maxf(ext.x, 1.0), map_size.y / maxf(ext.y, 1.0)) * 0.8
	var off := Vector2(size.x * 0.76, size.y * 0.5) - (mn + ext * 0.5) * sc
	var mapped := PackedVector2Array()
	var colors := PackedColorArray()
	for p in _pts:
		mapped.append(Vector2(p.x, p.z) * sc + off)
		var t := (p.y - ymin) / maxf(ymax - ymin, 1.0)
		colors.append(Color(0.35, 0.8, 1.0).lerp(Color(1.0, 0.55, 0.25), t) * line_color)
	var width := 4.0 if size.x > 300 else 2.0
	draw_polyline(mapped, Color(0, 0, 0, 0.5), width + 4.0, true)
	draw_polyline_colors(mapped, colors, width, true)
	draw_circle(mapped[0], width + 1.0, UITheme.ACCENT_2)
	var dir := (mapped[min(6, mapped.size() - 1)] - mapped[0]).normalized()
	var tip := mapped[0] + dir * width * 3.0
	draw_line(mapped[0], tip, Color.WHITE, 2.0, true)
	draw_colored_polygon(PackedVector2Array([tip + dir * width, tip + dir.orthogonal() * width, tip - dir.orthogonal() * width]), Color.WHITE)
