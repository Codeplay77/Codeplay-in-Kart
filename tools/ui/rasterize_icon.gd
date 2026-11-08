extends SceneTree
func _initialize() -> void:
	var image := Image.new()
	var err := image.load_svg_from_string(FileAccess.get_file_as_string("res://icon.svg"), 2.0)
	if err == OK:
		err = image.save_png("res://assets/ui/app_icon.png")
	quit(err)
