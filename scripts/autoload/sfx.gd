extends Node

const RATE := 48000
const REFINED := "res://assets/audio/refined/"
const REFINED_NAMES := ["beep", "go", "pickup", "item_ready", "drift_level", "boost", "hit", "shoot", "lap", "finish", "click", "confirm", "back", "crash", "bump", "cheer", "screech"]
const COOLDOWNS := {"crash": 0.16, "bump": 0.12, "boost": 0.12, "pickup": 0.07, "click": 0.045}
const TRIM_DB := {"crash": -2.0, "bump": -3.0, "hit": -2.0, "final_lap": -7.0}

const FILES := {
	"beep": "res://assets/audio/sfx/countdown_beep.wav",
	"go": "res://assets/audio/sfx/countdown_go.wav",
	"pickup": "res://assets/audio/sfx/item_pickup.wav",
	"boost": "res://assets/audio/sfx/boost.ogg",
	"hit": "res://assets/audio/sfx/item_hit.wav",
	"crash": "res://assets/audio/sfx/crash.wav",
	"bump": "res://assets/audio/sfx/bump.wav",
	"cheer": "res://assets/audio/sfx/crowd_cheer.ogg",
	"screech": "res://assets/audio/sfx/skid_screech.ogg",
	"click": "res://assets/audio/sfx/ui_select.wav",
	"confirm": "res://assets/audio/sfx/ui_confirm.wav",
	"back": "res://assets/audio/sfx/ui_back.wav",
	"final_lap": "res://assets/audio/music/jingle_final_lap.ogg",
}

var sounds := {}
var _players: Array[AudioStreamPlayer] = []
var _last_play := {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for i in 8:
		var p := AudioStreamPlayer.new()
		p.bus = "SFX"
		add_child(p)
		_players.append(p)
	sounds.beep = _tone([[660.0, 0.16]], 0.35)
	sounds.go = _tone([[990.0, 0.45]], 0.4)
	sounds.pickup = _tone([[660.0, 0.06], [880.0, 0.06], [1320.0, 0.1]], 0.25)
	sounds.item_ready = _tone([[1046.0, 0.05], [1568.0, 0.12]], 0.22)
	sounds.drift_level = _tone([[1200.0, 0.07], [1800.0, 0.09]], 0.18)
	sounds.boost = _sweep(180.0, 900.0, 0.55, 0.45)
	sounds.hit = _noise_burst(0.45, 0.5, 900.0)
	sounds.shoot = _sweep(1400.0, 300.0, 0.25, 0.3)
	sounds.lap = _tone([[784.0, 0.1], [988.0, 0.1], [1175.0, 0.22]], 0.3)
	sounds.finish = _tone([[523.0, 0.14], [659.0, 0.14], [784.0, 0.14], [1046.0, 0.4]], 0.32)
	sounds.click = _tone([[1500.0, 0.03]], 0.15)
	for key: String in FILES:
		var path: String = FILES[key]
		if ResourceLoader.exists(path):
			sounds[key] = load(path)
	for key: String in REFINED_NAMES:
		var path := REFINED + key + ".wav"
		if ResourceLoader.exists(path):
			sounds[key] = load(path)


func play(name: String, pitch := 1.0, volume_db := 0.0) -> void:
	if not sounds.has(name):
		return
	var now := Time.get_ticks_msec() * 0.001
	if now - float(_last_play.get(name, -100.0)) < float(COOLDOWNS.get(name, 0.0)):
		return
	for p in _players:
		if not p.playing:
			p.stream = sounds[name]
			p.pitch_scale = clampf(pitch, 0.5, 2.0)
			p.volume_db = volume_db + float(TRIM_DB.get(name, 0.0))
			p.play()
			_last_play[name] = now
			return


func _wav(samples: PackedFloat32Array) -> AudioStreamWAV:
	var data := PackedByteArray()
	data.resize(samples.size() * 2)
	for i in samples.size():
		data.encode_s16(i * 2, int(clampf(samples[i], -1.0, 1.0) * 32767.0))
	var w := AudioStreamWAV.new()
	w.format = AudioStreamWAV.FORMAT_16_BITS
	w.mix_rate = RATE
	w.stereo = false
	w.data = data
	return w


func _tone(notes: Array, amp: float) -> AudioStreamWAV:
	var out := PackedFloat32Array()
	var phase := 0.0
	for n: Array in notes:
		var f: float = n[0]
		var count := int(float(n[1]) * RATE)
		for i in count:
			var t := float(i) / count
			phase += f / RATE
			var s := sin(phase * TAU) * 0.7 + sin(phase * TAU * 3.0) * 0.2 + sin(phase * TAU * 5.0) * 0.08
			var env := minf(1.0, t * 40.0) * (1.0 - t) ** 1.5
			out.append(s * env * amp)
	return _wav(out)


func _sweep(f0: float, f1: float, dur: float, amp: float) -> AudioStreamWAV:
	var out := PackedFloat32Array()
	var phase := 0.0
	var count := int(dur * RATE)
	for i in count:
		var t := float(i) / count
		phase += lerpf(f0, f1, t * t) / RATE
		var s := (fmod(phase, 1.0) * 2.0 - 1.0) * 0.5 + randf_range(-0.35, 0.35)
		var env := minf(1.0, t * 15.0) * (1.0 - t)
		out.append(s * env * amp)
	return _wav(_lowpass(out, 0.35))


func _noise_burst(dur: float, amp: float, cutoff: float) -> AudioStreamWAV:
	var out := PackedFloat32Array()
	var count := int(dur * RATE)
	for i in count:
		var t := float(i) / count
		out.append(randf_range(-1.0, 1.0) * (1.0 - t) ** 2.0 * amp)
	return _wav(_lowpass(out, clampf(cutoff / RATE * 6.0, 0.02, 1.0)))


func _lowpass(x: PackedFloat32Array, k: float) -> PackedFloat32Array:
	var y := 0.0
	for i in x.size():
		y += (x[i] - y) * k
		x[i] = y
	return x
