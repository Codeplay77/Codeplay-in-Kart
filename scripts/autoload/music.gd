extends Node

const DIR := "res://assets/audio/music/"
const MENU: Array[String] = ["v2/menu_apple_cider.ogg"]
const RACE_BY_THEME := {
	"valley": ["v2/drive.ogg", "v2/sideways_city.ogg"],
	"desert": ["v2/microwave.ogg", "v2/drive.ogg"],
	"beach": ["v2/happy_ukulele_island_surfing.ogg", "v2/sideways_city.ogg"],
	"autumn": ["v2/empty_stretch.ogg", "v2/drive.ogg"],
	"snow": ["v2/black_diamond.ogg"],
	"canyon": ["v2/super_wreck_roadway.ogg", "v2/microwave.ogg"],
	"night": ["v2/raspberry_jam.ogg", "v2/sideways_city.ogg"],
	"moor": ["v2/synesthesia.ogg"],
	"volcano": ["v2/super_wreck_roadway.ogg"],
}
const RACE: Array[String] = ["v2/drive.ogg", "v2/empty_stretch.ogg", "v2/sideways_city.ogg"]
const VICTORY: Array[String] = ["v2/podium_funky_victory_loop.ogg"]
const LEVELS := preload("res://scripts/audio/music_levels.gd")
const MIX_TRIM_DB := -4.0
const JINGLE_WIN := "jingle_finish_win.ogg"
const JINGLE_GOOD := "jingle_finish_good.ogg"
const JINGLE_LOSE := "jingle_finish_lose.ogg"
const FADE := 1.2

var _players: Array[AudioStreamPlayer] = []
var _active := 0
var _current := ""
var _tween: Tween


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for i in 2:
		var p := AudioStreamPlayer.new()
		p.bus = "Music"
		p.volume_db = -80.0
		add_child(p)
		_players.append(p)


func play_menu() -> void:
	if _current in MENU and _players[_active].playing:
		return
	_play(_pick(MENU, randi()))


func play_race(track_id: String) -> void:
	var theme_id: String = TrackCatalog.get_def(track_id).get("theme", "")
	var list: Array[String] = []
	list.assign(RACE_BY_THEME.get(theme_id, RACE))
	var same := TrackCatalog.TRACKS.keys().filter(func(t: String) -> bool: return TrackCatalog.TRACKS[t].theme == theme_id)
	_play(_pick(list, maxi(same.find(track_id), 0)))


func play_victory() -> void:
	_play(_pick(VICTORY, randi()))


func play_finish(place: int, total: int) -> void:
	var jingle := JINGLE_WIN if place <= 3 else (JINGLE_GOOD if place <= maxi(total / 2, 4) else JINGLE_LOSE)
	if not ResourceLoader.exists(DIR + jingle):
		return
	_play(jingle, false)
	var p := _players[_active]
	var token := _current
	await p.finished
	if _current == token:
		if place <= 3:
			play_victory()
		else:
			_current = ""


func stop(fade := FADE) -> void:
	_current = ""
	_fade_out(fade)


func _pick(list: Array[String], seed_value: int) -> String:
	var valid: Array[String] = []
	for f in list:
		if ResourceLoader.exists(DIR + f):
			valid.append(f)
	if valid.is_empty():
		return ""
	return valid[absi(seed_value) % valid.size()]


func _play(file: String, loop := true) -> void:
	if file == "":
		return
	if file == _current and _players[_active].playing:
		return
	var stream := load(DIR + file) as AudioStream
	if stream == null:
		return
	if stream is AudioStreamOggVorbis:
		stream = stream.duplicate()
		(stream as AudioStreamOggVorbis).loop = loop
	elif stream is AudioStreamMP3:
		stream = stream.duplicate()
		(stream as AudioStreamMP3).loop = loop
	_current = file
	var old := _players[_active]
	_active = 1 - _active
	var p := _players[_active]
	p.stream = stream
	p.volume_db = -80.0
	p.play()
	if _tween:
		_tween.kill()
	var target_gain := db_to_linear(float(LEVELS.GAIN_DB.get(file, MIX_TRIM_DB)))
	var old_gain := db_to_linear(old.volume_db) if old.playing else 0.0
	# Equal-power amplitude curves avoid the deep dip caused by interpolating dB.
	_tween = create_tween()
	_tween.tween_method(_crossfade.bind(p, old, target_gain, old_gain), 0.0, 1.0, FADE)
	_tween.tween_callback(old.stop)


func _crossfade(progress: float, incoming: AudioStreamPlayer, outgoing: AudioStreamPlayer, target_gain: float, old_gain: float) -> void:
	_set_amplitude(incoming, sin(progress * PI * 0.5) * target_gain)
	_set_amplitude(outgoing, cos(progress * PI * 0.5) * old_gain)


func _set_amplitude(player: AudioStreamPlayer, amplitude: float) -> void:
	player.volume_db = linear_to_db(maxf(amplitude, 0.0001))


func _fade_out(fade: float) -> void:
	if _tween:
		_tween.kill()
	_tween = create_tween()
	# Both players may be audible if stop interrupts a crossfade.
	for player in _players:
		if player.playing:
			_tween.parallel().tween_method(_fade_amplitude.bind(player, db_to_linear(player.volume_db)), 0.0, 1.0, fade)
	_tween.chain().tween_callback(func() -> void:
		for player in _players:
			player.stop())


func _fade_amplitude(progress: float, player: AudioStreamPlayer, start_gain: float) -> void:
	_set_amplitude(player, cos(progress * PI * 0.5) * start_gain)
