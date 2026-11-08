class_name EngineAudio
extends Node3D

const SFX_DIR := "res://assets/audio/sfx/"
const REFINED_DIR := "res://assets/audio/refined/"
const GEAR_SPEED := 9.0 # m/s por marcha
const RATE := 22050.0
## Conjuntos de som de motor (escolha em Opções > Áudio). Cada um: camadas
## [arquivo em SFX_DIR, frequência fundamental medida (Hz)] do MESMO motor gravado em várias
## rotações, da mais grave à mais aguda, e a faixa de frequência [mín, máx] percorrida da
## marcha lenta à rotação máxima. O pitch de cada camada segue a "rotação" e as vizinhas fazem
## crossfade de potência constante. Ver assets/audio/AUDIO_CREDITS.md.
const ENGINE_SETS := {
	"kart": {"label": "Kart 2 tempos", "range": [108.0, 245.0], "layers": [
		["engine/alt_2stroke_bike/engine_rpm1", 166.8],
		["engine/alt_2stroke_bike/engine_rpm2", 182.4],
		["engine/alt_2stroke_bike/engine_rpm3", 201.5]]},
	"car": {"label": "Carro", "range": [25.0, 98.0], "layers": [
		["engine/engine_rpm1", 27.9], ["engine/engine_rpm2", 49.3],
		["engine/engine_rpm3", 67.0], ["engine/engine_rpm4", 85.0]]},
	"truck": {"label": "Picape", "range": [25.0, 112.0], "layers": [
		["engine/alt_4stroke_truck/engine_rpm1", 28.3],
		["engine/alt_4stroke_truck/engine_rpm2", 68.7],
		["engine/alt_4stroke_truck/engine_rpm3", 98.0]]},
	"classic": {"label": "Clássico", "range": [30.0, 104.0], "layers": [
		["engine_idle", 37.0], ["engine_high", 90.0]]},
}
const DEFAULT_SET := "kart"

var kart: Kart
var is_player := true

var _layers: Array = [] # [player, hz]
var _skid: Node
var _rev := 0.0
var _skid_amt := 0.0
var _gain := 0.0
var _f_min := 30.0
var _f_max := 104.0
var _flutter := 0.0
var _gear := 0
var _shift_cooldown := 0.0
var _throttle := 0.0

var _gen_player: AudioStreamPlayer
var _playback: AudioStreamGeneratorPlayback
var _phase := 0.0
var _sub := 0.0
var _freq := 50.0
var _squeal := 0.0
var _squeal_phase := 0.0
var _lp := 0.0


func _ready() -> void:
	_gain = -3.5 if is_player else -16.0
	var set_id := str(Settings.get_value("audio", "engine_sound", DEFAULT_SET))
	var cfg: Dictionary = ENGINE_SETS.get(set_id, ENGINE_SETS[DEFAULT_SET])
	var layers: Array = cfg.layers
	var lite := Settings.is_mobile() and not is_player
	if lite:
		layers = [cfg.layers[cfg.layers.size() / 2]]
	for layer: Array in layers:
		var st := _load_loop(layer[0])
		if st:
			_layers.append([_make_player(st, "Engine"), float(layer[1])])
	_f_min = float(cfg.range[0])
	_f_max = float(cfg.range[1])
	if _layers.is_empty() and is_player:
		_start_synth()
	var skid := _load_loop("skid_loop")
	if skid and not lite:
		_skid = _make_player(skid, "SFX")


func _load_loop(file: String) -> AudioStream:
	var paths: Array[String] = [REFINED_DIR + file + ".wav", SFX_DIR + file + ".ogg", SFX_DIR + file + ".wav"]
	for path: String in paths:
		if ResourceLoader.exists(path):
			var st := load(path) as AudioStream
			# O loop dos .wav é definido na importação (edit/loop_mode=2 no .import).
			# NÃO ligar o loop de AudioStreamWAV em tempo de execução: calcular loop_end pela
			# duração lia além do fim dos dados e derrubava o app no Android (SIGSEGV na
			# thread de áudio).
			if st is AudioStreamOggVorbis:
				(st as AudioStreamOggVorbis).loop = true
			return st
	return null


func _make_player(stream: AudioStream, bus: String) -> Node:
	var p: Node
	if is_player:
		var p2 := AudioStreamPlayer.new()
		p2.stream = stream
		p2.bus = bus
		p2.volume_db = -80.0
		p = p2
	else:
		var p3 := AudioStreamPlayer3D.new()
		p3.stream = stream
		p3.bus = bus
		p3.volume_db = -80.0
		p3.unit_size = 4.0
		p3.max_distance = 48.0
		p3.attenuation_filter_cutoff_hz = 6000.0
		p3.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_PHYSICS_STEP
		p = p3
	add_child(p)
	# Começa em pontos diferentes do loop para os karts não soarem em uníssono.
	p.call("play", randf() * stream.get_length() * 0.8)
	return p


func _process(delta: float) -> void:
	if kart == null:
		return
	var spd := absf(kart.forward_speed)
	# Hysteresis prevents gear chatter when speed hovers around a shift point.
	_shift_cooldown = maxf(0.0, _shift_cooldown - delta)
	if _shift_cooldown <= 0.0:
		if _gear < 4 and spd > (_gear + 1) * GEAR_SPEED + 0.9:
			_gear += 1
			_shift_cooldown = 0.3
		elif _gear > 0 and spd < _gear * GEAR_SPEED - 1.4:
			_gear -= 1
			_shift_cooldown = 0.3
	var in_gear := clampf((spd - _gear * GEAR_SPEED) / GEAR_SPEED, 0.0, 1.0)
	_throttle = lerpf(_throttle, clampf(absf(kart.in_throttle), 0.0, 1.0), 1.0 - exp(-8.0 * delta))
	var target := 0.08 + in_gear * 0.52 + _gear * 0.065 + _throttle * 0.12
	if kart.is_boosting():
		target += 0.15
	if not kart.grounded:
		target += 0.12 * _throttle
	target = clampf(target, 0.0, 1.0)
	var rate := 7.0 if target > _rev else 10.0
	_rev = lerpf(_rev, target, 1.0 - exp(-rate * delta))
	_flutter = lerpf(_flutter, randf_range(-1.0, 1.0), 1.0 - exp(-20.0 * delta))
	var load_db := lerpf(-7.0, 0.0, _throttle)
	var f := lerpf(_f_min, _f_max, _rev) * (1.0 + _flutter * 0.0025)

	if not _layers.is_empty():
		var n := _layers.size()
		for i in n:
			var hz: float = _layers[i][1]
			var w := 0.0
			var lo: float = _layers[i - 1][1] if i > 0 else -INF
			var hi: float = _layers[i + 1][1] if i < n - 1 else INF
			if f <= hz:
				w = 1.0 if i == 0 else clampf((f - lo) / (hz - lo), 0.0, 1.0)
			else:
				w = 1.0 if i == n - 1 else clampf((hi - f) / (hi - hz), 0.0, 1.0)
			var amp := sin(w * PI * 0.5)
			_apply_player(_layers[i][0], f / hz, linear_to_db(maxf(amp, 0.0001)) + load_db, delta)

	var drifting := kart.grounded and (kart.drift_dir != 0 or kart.spin_time > 0.0) and spd > 6.0
	_skid_amt = lerpf(_skid_amt, 1.0 if drifting else 0.0, 1.0 - exp(-(14.0 if drifting else 8.0) * delta))
	if _skid:
		var wobble := 1.0 + sin(Time.get_ticks_msec() * 0.011) * 0.03
		_apply_player(_skid, (0.92 + clampf(spd / 40.0, 0.0, 0.2)) * wobble, linear_to_db(maxf(_skid_amt, 0.0001)) - 6.0, delta)
	if _gen_player:
		_synth(delta)


func _apply_player(p: Node, pitch: float, vol_db: float, delta: float) -> void:
	var smoothing := 1.0 - exp(-18.0 * delta)
	p.set("pitch_scale", lerpf(float(p.get("pitch_scale")), clampf(pitch, 0.4, 2.5), smoothing))
	# Interpolate amplitude instead of jumping volume on every render frame.
	var amplitude := lerpf(db_to_linear(float(p.get("volume_db"))), db_to_linear(vol_db + _gain), smoothing)
	p.set("volume_db", linear_to_db(maxf(amplitude, 0.0001)))


func _start_synth() -> void:
	_gen_player = AudioStreamPlayer.new()
	var gen := AudioStreamGenerator.new()
	gen.mix_rate = RATE
	gen.buffer_length = 0.1
	_gen_player.stream = gen
	_gen_player.bus = "Engine"
	_gen_player.volume_db = -9.0
	add_child(_gen_player)
	_gen_player.play()
	_playback = _gen_player.get_stream_playback()


func _synth(delta: float) -> void:
	var spd := absf(kart.forward_speed)
	var gear := floorf(spd / GEAR_SPEED)
	var in_gear := fmod(spd, GEAR_SPEED) / GEAR_SPEED
	var target := 46.0 + in_gear * 58.0 + gear * 9.0 + kart.in_throttle * 10.0
	if kart.is_boosting():
		target += 25.0
	if not kart.grounded:
		target += 20.0 * kart.in_throttle
	_freq = lerpf(_freq, target, 1.0 - exp(-10.0 * delta))
	var squeal_target := 0.09 if (kart.drift_dir != 0 and kart.grounded and _skid == null) else 0.0
	_squeal = lerpf(_squeal, squeal_target, 1.0 - exp(-12.0 * delta))
	var amp := 0.22 + kart.in_throttle * 0.12
	var n := _playback.get_frames_available()
	for i in n:
		_phase = fmod(_phase + _freq / RATE, 1.0)
		_sub = fmod(_sub + _freq * 0.5 / RATE, 1.0)
		var saw := _phase * 2.0 - 1.0
		var pulse := 1.0 if _sub < 0.32 else -1.0
		var s := saw * 0.55 + pulse * 0.3 + randf_range(-0.12, 0.12)
		_lp += (s - _lp) * 0.28
		var out := tanh(_lp * 1.8) * amp
		if _squeal > 0.001:
			_squeal_phase += (1150.0 + randf_range(-90.0, 90.0)) / RATE
			out += sin(_squeal_phase * TAU) * _squeal
		_playback.push_frame(Vector2(out, out))
