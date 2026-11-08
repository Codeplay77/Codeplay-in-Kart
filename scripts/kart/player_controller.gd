class_name PlayerController
extends RefCounted


func update(kart: Kart, _delta: float) -> void:
	kart.in_throttle = Input.get_action_strength("accelerate")
	kart.in_brake = Input.get_action_strength("brake")
	kart.in_steer = Input.get_axis("steer_left", "steer_right")
	kart.in_drift = Input.is_action_pressed("drift")
	if Input.is_action_just_pressed("use_item"):
		kart.in_item = true
