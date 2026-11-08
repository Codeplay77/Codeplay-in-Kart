class_name ThemedTrack
extends Track

var track_id := ""


func _ready() -> void:
	var def := TrackCatalog.get_def(track_id)
	theme = TrackThemes.resolve(def.theme, def.get("overrides", {}))
	decoration_seed = hash(track_id) % 100000
	super._ready()


func _layout_points() -> PackedVector3Array:
	return PackedVector3Array(TrackLayouts.LAYOUTS[track_id].points)


func _layout_features() -> void:
	var lay: Dictionary = TrackLayouts.LAYOUTS[track_id]
	for f: float in lay.items:
		add_item_row(length * f)
	for b: Array in lay.boosts:
		add_boost_pad(length * float(b[0]), float(b[1]))
	for r: Array in lay.ramps:
		add_ramp(length * float(r[0]), float(r[1]))
		add_boost_pad(length * float(r[0]) - 9.0, float(r[1]))
