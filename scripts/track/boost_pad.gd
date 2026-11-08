extends Area3D

const SIZE := Vector2(4.0, 6.0)


func _ready() -> void:
	collision_layer = Kart.LAYER_ITEMS
	collision_mask = Kart.LAYER_KART
	monitorable = false
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(SIZE.x, 1.6, SIZE.y)
	cs.shape = bs
	cs.position.y = 0.8
	add_child(cs)
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = SIZE
	var mat := ShaderMaterial.new()
	mat.shader = load("res://scripts/track/boost_pad.gdshader")
	pm.material = mat
	mi.mesh = pm
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node3D) -> void:
	if body is Kart:
		(body as Kart).apply_boost(1.1, 0.9)
