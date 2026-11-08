class_name MineItem
extends Area3D

const ARM_TIME := 0.5
const LIFETIME := 45.0

var owner_kart: Kart
var _age := 0.0
var _mesh: MeshInstance3D
var _light_mat: StandardMaterial3D


static func spawn(parent: Node, from: Kart) -> MineItem:
	var m := MineItem.new()
	m.owner_kart = from
	parent.add_child(m)
	var back := -from.get_forward()
	var p := from.global_position + back * 2.0
	var space := from.get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(p + Vector3.UP * 2.0, p + Vector3.DOWN * 6.0, Kart.LAYER_TRACK)
	var hit := space.intersect_ray(q)
	m.global_position = (hit.position as Vector3) if hit else p
	return m


func _ready() -> void:
	collision_layer = Kart.LAYER_ITEMS
	collision_mask = Kart.LAYER_KART
	var cs := CollisionShape3D.new()
	var s := SphereShape3D.new()
	s.radius = 0.9
	cs.shape = s
	cs.position.y = 0.4
	add_child(cs)
	_mesh = MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.45
	sm.height = 0.5
	sm.is_hemisphere = true
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.12, 0.12, 0.14)
	m.metallic = 0.8
	m.roughness = 0.3
	sm.material = m
	_mesh.mesh = sm
	add_child(_mesh)
	var dot := MeshInstance3D.new()
	var dm := SphereMesh.new()
	dm.radius = 0.12
	dm.height = 0.24
	_light_mat = StandardMaterial3D.new()
	_light_mat.albedo_color = Color.RED
	_light_mat.emission_enabled = true
	_light_mat.emission = Color.RED
	_light_mat.emission_energy_multiplier = 4.0
	dm.material = _light_mat
	dot.mesh = dm
	dot.position.y = 0.45
	add_child(dot)
	body_entered.connect(_on_body_entered)


func _process(delta: float) -> void:
	_age += delta
	_light_mat.emission_energy_multiplier = 1.0 + 5.0 * (0.5 + 0.5 * sin(_age * 9.0))
	if _age > LIFETIME:
		queue_free()


func _on_body_entered(body: Node3D) -> void:
	if _age < ARM_TIME and body == owner_kart:
		return
	if body is Kart:
		(body as Kart).hit()
		Effects.burst(get_parent(), global_position + Vector3.UP * 0.5, Color(1.0, 0.5, 0.1))
		queue_free()
