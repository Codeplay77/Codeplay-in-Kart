class_name OrbProjectile
extends Area3D

const SPEED := 52.0
const LIFETIME := 5.0

var owner_kart: Kart
var direction := Vector3.FORWARD
var _age := 0.0
var _vy := 0.0


static func spawn(parent: Node, from: Kart) -> OrbProjectile:
	var o := OrbProjectile.new()
	o.owner_kart = from
	o.direction = from.get_forward()
	parent.add_child(o)
	o.global_position = from.global_position + o.direction * 2.0 + Vector3.UP * 0.3
	return o


func _ready() -> void:
	collision_layer = Kart.LAYER_ITEMS
	collision_mask = Kart.LAYER_KART
	var cs := CollisionShape3D.new()
	var s := SphereShape3D.new()
	s.radius = 0.7
	cs.shape = s
	add_child(cs)
	var mi := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.38
	sm.height = 0.76
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.4, 1.0, 0.9)
	m.emission_enabled = true
	m.emission = Color(0.2, 1.0, 0.85)
	m.emission_energy_multiplier = 4.0
	sm.material = m
	mi.mesh = sm
	add_child(mi)
	var light := OmniLight3D.new()
	light.light_color = Color(0.3, 1.0, 0.9)
	light.light_energy = 2.0
	light.omni_range = 5.0
	add_child(light)
	body_entered.connect(_on_body_entered)


func _physics_process(delta: float) -> void:
	_age += delta
	if _age > LIFETIME:
		queue_free()
		return
	var space := get_world_3d().direct_space_state
	var best: Kart = null
	var best_d := 35.0
	for k: Kart in get_tree().get_nodes_in_group("karts"):
		if k == owner_kart and _age < 1.0:
			continue
		var to := k.global_position - global_position
		var d := to.length()
		if d < best_d and direction.dot(to.normalized()) > 0.5:
			best_d = d
			best = k
	if best:
		var want := (best.global_position - global_position)
		want.y = 0.0
		direction = direction.slerp(want.normalized(), 1.0 - exp(-4.0 * delta)).normalized()
	var step := direction * SPEED * delta
	var q := PhysicsRayQueryParameters3D.create(global_position, global_position + step * 1.5, Kart.LAYER_TRACK)
	var hit := space.intersect_ray(q)
	if hit and (hit.normal as Vector3).y < 0.5:
		var n: Vector3 = hit.normal
		n.y = 0.0
		direction = direction.bounce(n.normalized()).normalized()
		direction.y = 0.0
	global_position += direction * SPEED * delta
	var gq := PhysicsRayQueryParameters3D.create(global_position + Vector3.UP * 3.0, global_position + Vector3.DOWN * 6.0, Kart.LAYER_TRACK)
	var g := space.intersect_ray(gq)
	if g:
		var target_y: float = (g.position as Vector3).y + 0.55
		global_position.y = lerpf(global_position.y, target_y, 1.0 - exp(-20.0 * delta))
	else:
		_vy -= 30.0 * delta
		global_position.y += _vy * delta


func _on_body_entered(body: Node3D) -> void:
	if body is Kart and (body != owner_kart or _age > 0.4):
		(body as Kart).hit()
		Effects.burst(get_parent(), global_position, Color(0.3, 1.0, 0.9))
		queue_free()
