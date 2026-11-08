extends Track


func _theme_id() -> String:
	return "valley"


func _layout_points() -> PackedVector3Array:
	return PackedVector3Array([
		Vector3(0, 0, 40),
		Vector3(0, 0, -40),
		Vector3(0, 0.5, -110),
		Vector3(18, 1.0, -165),
		Vector3(65, 2.5, -192),
		Vector3(125, 5.0, -182),
		Vector3(178, 8.0, -150),
		Vector3(216, 9.5, -100),
		Vector3(226, 9.0, -45),
		Vector3(202, 7.0, 2),
		Vector3(160, 5.0, 26),
		Vector3(138, 3.5, 72),
		Vector3(160, 3.0, 122),
		Vector3(150, 4.5, 168),
		Vector3(112, 6.0, 192),
		Vector3(72, 3.0, 204),
		Vector3(34, 1.0, 192),
		Vector3(8, 0.2, 150),
		Vector3(0, 0, 100),
	])


func _layout_features() -> void:
	for f: float in [0.17, 0.46, 0.74]:
		add_item_row(length * f)
	add_boost_pad(length * 0.07, 0.4)
	add_boost_pad(length * 0.36, -0.35)
	add_boost_pad(length * 0.6, 0.0)
	var crest := curve.get_closest_offset(Vector3(112, 6.0, 192))
	add_ramp(crest - 20.0, 0.38)
	add_boost_pad(crest - 29.0, 0.38)
