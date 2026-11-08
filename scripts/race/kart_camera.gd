class_name KartCamera
extends Camera3D

var target: Kart
var distance := 5.6
var height := 2.1
var base_fov := 72.0

var _fwd := Vector3.FORWARD
var _shake := 0.0


func _ready() -> void:
	physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	top_level = true
	fov = base_fov
	far = 1500.0
	near = 0.1


func shake(amount: float) -> void:
	_shake = maxf(_shake, amount)


func snap() -> void:
	if target:
		_fwd = _flat(target.get_forward())
		_update(0.0, true)


func _process(delta: float) -> void:
	if target:
		_update(delta, false)


func _flat(v: Vector3) -> Vector3:
	v.y = 0.0
	return v.normalized() if v.length() > 0.01 else Vector3.FORWARD


func _update(delta: float, instant: bool) -> void:
	var pos := target.get_global_transform_interpolated().origin
	var f := _flat(target.get_forward())
	var k := 1.0 if instant else 1.0 - exp(-5.5 * delta)
	_fwd = _fwd.slerp(f, k).normalized() if _fwd.dot(f) > -0.99 else f
	var dir := _fwd
	if Input.is_action_pressed("look_back"):
		dir = -dir
	var speed_t := clampf(absf(target.forward_speed) / 40.0, 0.0, 1.0)
	var cs := Settings.camera_distance_scale()
	var desired: Vector3 = pos - dir * (distance + speed_t * 0.8) * cs + Vector3.UP * height * lerpf(1.0, cs, 0.6)
	var look: Vector3 = pos + dir * 4.0 + Vector3.UP * 0.9
	var space := get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(desired + Vector3.UP * 4.0, desired + Vector3.DOWN * 4.0, Kart.LAYER_TRACK)
	var hit := space.intersect_ray(q)
	if hit:
		desired.y = maxf(desired.y, (hit.position as Vector3).y + 0.8)
	if instant:
		global_position = desired
	else:
		global_position = global_position.lerp(desired, 1.0 - exp(-14.0 * delta))
	if _shake > 0.0:
		_shake = maxf(0.0, _shake - delta * 2.5)
		global_position += Vector3(randf_range(-1, 1), randf_range(-1, 1), randf_range(-1, 1)) * _shake * 0.25
	look_at(look, Vector3.UP)
	var target_fov := base_fov + clampf(absf(target.forward_speed) / 40.0, 0.0, 1.0) * 6.0
	if target.is_boosting():
		target_fov += 10.0
	fov = target_fov if instant else lerpf(fov, target_fov, 1.0 - exp(-4.0 * delta))
