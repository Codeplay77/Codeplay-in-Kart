class_name Track
extends Node3D
## Uma pista é definida por uma lista de pontos de controle (laço fechado). A partir dela
## são gerados: malha do asfalto com zebras e inclinação automática nas curvas, terreno
## com vale e colinas que se encaixa na pista, guard-rails com colisão, itens, placas de
## turbo, rampa e decoração. Para criar uma pista nova, estenda esta classe e
## sobrescreva `_layout_points()` (e opcionalmente `_layout_features()` e `_setup_environment()`).

const TEX := "res://assets/textures/"
const PROPS := "res://assets/models/props/"
const ItemBoxScript := preload("res://scripts/track/item_box.gd")
const BoostPadScript := preload("res://scripts/track/boost_pad.gd")
const WALL_HEIGHT := 9.0

@export var road_width := 15.0
@export var sample_step := 1.5
@export var wall_distance := 8.5
@export var decoration_seed := 1234
@export var decoration_density := 1.0

var curve := Curve3D.new()
var length := 0.0
var frames: Array[Transform3D] = []
var banks := PackedFloat32Array()
var _step := 1.0

var _g_origin := Vector2.ZERO
var _g_cell := 3.0
var _g_w := 0
var _g_h := 0
var _g_height := PackedFloat32Array()
var _g_dist := PackedFloat32Array()
var _g_idx := PackedInt32Array()

var theme: Dictionary = {}
var liquid_y := -INF
var _ramps: Array = []
var _noise := FastNoiseLite.new()
var _noise_big := FastNoiseLite.new()
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	if theme.is_empty():
		theme = TrackThemes.resolve(_theme_id())
	decoration_density *= Settings.decoration_density()
	_build_curve()
	_build_frames()
	_build_road()
	_build_terrain()
	_build_shoulders()
	_build_walls()
	_build_liquid()
	_build_lamps()
	_build_start_line()
	_layout_features()
	_decorate()
	_setup_environment()


func _layout_points() -> PackedVector3Array:
	return PackedVector3Array([
		Vector3(0, 0, 60), Vector3(0, 0, -60), Vector3(60, 0, -90),
		Vector3(110, 0, -40), Vector3(100, 0, 50), Vector3(50, 0, 90),
	])


func _theme_id() -> String:
	return "valley"


func _layout_features() -> void:
	for f: float in [0.2, 0.5, 0.8]:
		add_item_row(length * f)


## Transform da linha central no deslocamento `offset` (metros ao longo da pista).
## basis.x = direita, basis.y = cima (com inclinação), -basis.z = sentido da corrida.
func sample(offset: float) -> Transform3D:
	var o := fposmod(offset, length)
	var f := o / _step
	var i0 := int(f) % frames.size()
	var i1 := (i0 + 1) % frames.size()
	return frames[i0].interpolate_with(frames[i1], f - floorf(f))


func get_offset(world_pos: Vector3) -> float:
	return curve.get_closest_offset(to_local(world_pos))


func get_grid_transform(slot: int) -> Transform3D:
	var row := slot / 2
	var side := -1.0 if slot % 2 == 0 else 1.0
	var off := -9.0 - row * 7.5 - (slot % 2) * 3.0
	var xf := sample(off)
	xf.origin += xf.basis.x * side * road_width * 0.22
	return xf


func get_respawn_transform(offset: float) -> Transform3D:
	var xf := sample(offset)
	xf.origin += xf.basis.y * 0.4
	return xf


func get_minimap_points(step := 6.0) -> PackedVector2Array:
	var out := PackedVector2Array()
	var o := 0.0
	while o < length:
		var p := sample(o).origin
		out.append(Vector2(p.x, p.z))
		o += step
	return out


func terrain_height(x: float, z: float) -> float:
	var gx := clampf((x - _g_origin.x) / _g_cell, 0.0, _g_w - 1.001)
	var gz := clampf((z - _g_origin.y) / _g_cell, 0.0, _g_h - 1.001)
	var ix := int(gx)
	var iz := int(gz)
	var fx := gx - ix
	var fz := gz - iz
	var h00 := _g_height[iz * _g_w + ix]
	var h10 := _g_height[iz * _g_w + ix + 1]
	var h01 := _g_height[(iz + 1) * _g_w + ix]
	var h11 := _g_height[(iz + 1) * _g_w + ix + 1]
	return lerpf(lerpf(h00, h10, fx), lerpf(h01, h11, fx), fz)


func distance_to_road(x: float, z: float) -> float:
	var ix := clampi(int(roundf((x - _g_origin.x) / _g_cell)), 0, _g_w - 1)
	var iz := clampi(int(roundf((z - _g_origin.y) / _g_cell)), 0, _g_h - 1)
	return _g_dist[iz * _g_w + ix]


func _build_curve() -> void:
	var pts := _layout_points()
	var n := pts.size()
	curve.clear_points()
	curve.bake_interval = 0.5
	var tangents: Array[Vector3] = []
	for i in n:
		var p0 := pts[(i - 1 + n) % n]
		var p2 := pts[(i + 1) % n]
		tangents.append((p2 - p0) / 6.0)
	for i in n:
		curve.add_point(pts[i], -tangents[i], tangents[i])
	curve.add_point(pts[0], -tangents[0], tangents[0])
	length = curve.get_baked_length()


func _build_frames() -> void:
	var count := int(length / sample_step)
	_step = length / count
	var origins: Array[Vector3] = []
	var fwds: Array[Vector3] = []
	var headings := PackedFloat32Array()
	for i in count:
		var o := i * _step
		origins.append(curve.sample_baked(o, true))
		var a := curve.sample_baked(fposmod(o - 1.0, length), true)
		var b := curve.sample_baked(fposmod(o + 1.0, length), true)
		var f := (b - a).normalized()
		fwds.append(f)
		headings.append(atan2(f.x, f.z))
	var k := 6
	var raw := PackedFloat32Array()
	raw.resize(count)
	for i in count:
		var h0 := headings[(i - k + count) % count]
		var h1 := headings[(i + k) % count]
		var curvature := angle_difference(h0, h1) / (2.0 * k * _step)
		raw[i] = clampf(-curvature * 6.5, -0.2, 0.2)
	banks.resize(count)
	var win := 14
	for i in count:
		var s := 0.0
		for j in range(-win, win + 1):
			s += raw[(i + j + count) % count]
		banks[i] = s / (2 * win + 1)
	frames.clear()
	for i in count:
		var f := fwds[i]
		var up := (Vector3.UP - f * f.y).normalized().rotated(f, banks[i])
		var right := f.cross(up).normalized()
		up = right.cross(f).normalized()
		frames.append(Transform3D(Basis(right, up, -f), origins[i]))


func _extrude(profile: Array, us: Array, v_scale: float, close_loop := true) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var count := frames.size()
	var rows := count + (1 if close_loop else 0)
	var np := profile.size()
	for i in rows:
		var fr := frames[i % count]
		var dist := i * _step
		for k in np:
			var pr: Vector2 = profile[k]
			st.set_uv(Vector2(us[k], dist * v_scale))
			st.add_vertex(fr.origin + fr.basis.x * pr.x + fr.basis.y * pr.y)
	for i in rows - 1:
		for k in np - 1:
			var a := i * np + k
			var b := a + 1
			var c := a + np
			var d := c + 1
			st.add_index(a); st.add_index(c); st.add_index(d)
			st.add_index(a); st.add_index(d); st.add_index(b)
	st.generate_normals()
	st.generate_tangents()
	return st.commit()


## Conjunto de texturas no formato "pasta/id@2k" ou "id@1k" (pasta = id).
static func tex_paths(set_name: String) -> Dictionary:
	var res := "2k"
	var path := set_name
	if set_name.contains("@"):
		path = set_name.get_slice("@", 0)
		res = set_name.get_slice("@", 1)
	var folder := path.get_base_dir() if path.contains("/") else path
	var id := path.get_file()
	var base := TEX + folder + "/" + id
	return {
		"albedo": base + "_diff_%s.jpg" % res,
		"normal": base + "_nor_gl_%s.jpg" % res,
		"arm": base + "_arm_%s.jpg" % res,
	}


func _tex_material(set_name: String, tint := Color.WHITE) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	var p := tex_paths(set_name)
	if ResourceLoader.exists(p.albedo):
		m.albedo_texture = load(p.albedo)
		m.normal_enabled = true
		m.normal_texture = load(p.normal)
		m.roughness_texture = load(p.arm)
		m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
		m.ao_enabled = true
		m.ao_texture = load(p.arm)
		m.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	m.albedo_color = tint
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	return m


static func stripe_texture(c1: Color, c2: Color) -> ImageTexture:
	var img := Image.create(2, 2, false, Image.FORMAT_RGBA8)
	img.set_pixel(0, 0, c1); img.set_pixel(1, 0, c1)
	img.set_pixel(0, 1, c2); img.set_pixel(1, 1, c2)
	return ImageTexture.create_from_image(img)


func _build_road() -> void:
	var hw := road_width * 0.5
	var road_body := StaticBody3D.new()
	road_body.name = "Road"
	road_body.collision_layer = Kart.LAYER_TRACK
	road_body.collision_mask = 0
	road_body.set_meta("surface", "road")
	add_child(road_body)

	var road_mesh := _extrude(
		[Vector2(-hw, 0), Vector2(0, 0), Vector2(hw, 0)],
		[0.0, hw / 6.0, hw / 3.0], 1.0 / 6.0)
	var asphalt := _tex_material(theme.road, theme.road_tint)
	road_mesh.surface_set_material(0, asphalt)
	var road_mi := MeshInstance3D.new()
	road_mi.mesh = road_mesh
	road_body.add_child(road_mi)

	var curb_mat := StandardMaterial3D.new()
	curb_mat.albedo_texture = stripe_texture(theme.curb_a, theme.curb_b)
	if float(theme.curb_glow) > 0.0:
		curb_mat.emission_enabled = true
		curb_mat.emission_texture = curb_mat.albedo_texture
		curb_mat.emission_energy_multiplier = float(theme.curb_glow)
	curb_mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	curb_mat.roughness = 0.55
	var curb_w := 1.3
	for side: float in [-1.0, 1.0]:
		var prof := [
			Vector2(side * hw, 0.0), Vector2(side * (hw + 0.12), 0.07),
			Vector2(side * (hw + curb_w - 0.15), 0.07), Vector2(side * (hw + curb_w), 0.0),
		]
		if side < 0:
			prof.reverse()
		var curb := _extrude(prof, [0.0, 0.0, 0.0, 0.0], 1.0 / 5.0)
		curb.surface_set_material(0, curb_mat)
		var cmi := MeshInstance3D.new()
		cmi.mesh = curb
		road_body.add_child(cmi)
		var line_prof := [Vector2(side * (hw - 0.75), 0.012), Vector2(side * (hw - 0.45), 0.012)]
		if side < 0:
			line_prof.reverse()
		var line := _extrude(line_prof, [0.0, 1.0], 0.1)
		var line_mat := StandardMaterial3D.new()
		line_mat.albedo_color = theme.line_color
		line_mat.roughness = 0.6
		if float(theme.line_glow) > 0.0:
			line_mat.emission_enabled = true
			line_mat.emission = theme.line_color
			line_mat.emission_energy_multiplier = float(theme.line_glow)
		line.surface_set_material(0, line_mat)
		var lmi := MeshInstance3D.new()
		lmi.mesh = line
		lmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(lmi)
		var cs_curb := CollisionShape3D.new()
		cs_curb.shape = curb.create_trimesh_shape()
		road_body.add_child(cs_curb)

	var cs := CollisionShape3D.new()
	cs.shape = road_mesh.create_trimesh_shape()
	road_body.add_child(cs)


func _build_terrain() -> void:
	_noise.seed = decoration_seed
	_noise.frequency = 0.012
	_noise.fractal_octaves = 4
	_noise_big.seed = decoration_seed + 7
	_noise_big.frequency = 0.004
	var hw := road_width * 0.5

	var mn := Vector2(INF, INF)
	var mx := Vector2(-INF, -INF)
	for fr in frames:
		mn = mn.min(Vector2(fr.origin.x, fr.origin.z))
		mx = mx.max(Vector2(fr.origin.x, fr.origin.z))
	var margin := 190.0
	_g_origin = mn - Vector2(margin, margin)
	var size := (mx - mn) + Vector2(margin, margin) * 2.0
	_g_w = int(size.x / _g_cell) + 1
	_g_h = int(size.y / _g_cell) + 1
	var total := _g_w * _g_h

	# Transformada de distância (propaga o índice do ponto da pista mais próximo).
	_g_dist = PackedFloat32Array()
	_g_dist.resize(total)
	_g_dist.fill(INF)
	_g_idx = PackedInt32Array()
	_g_idx.resize(total)
	_g_idx.fill(-1)
	var fx := PackedFloat32Array()
	var fz := PackedFloat32Array()
	for fr in frames:
		fx.append(fr.origin.x)
		fz.append(fr.origin.z)
	for k in frames.size():
		var cx := int((fx[k] - _g_origin.x) / _g_cell)
		var cz := int((fz[k] - _g_origin.y) / _g_cell)
		for dz in range(-2, 3):
			for dx in range(-2, 3):
				var x := cx + dx
				var z := cz + dz
				if x < 0 or z < 0 or x >= _g_w or z >= _g_h:
					continue
				var c := z * _g_w + x
				var px := _g_origin.x + x * _g_cell
				var pz := _g_origin.y + z * _g_cell
				var d := Vector2(px - fx[k], pz - fz[k]).length()
				if d < _g_dist[c]:
					_g_dist[c] = d
					_g_idx[c] = k
	for pass_i in 2:
		var z_range := range(_g_h) if pass_i == 0 else range(_g_h - 1, -1, -1)
		var x_range := range(_g_w) if pass_i == 0 else range(_g_w - 1, -1, -1)
		var s := 1 if pass_i == 0 else -1
		var nbs := [Vector2i(-s, 0), Vector2i(0, -s), Vector2i(-s, -s), Vector2i(s, -s)]
		for z: int in z_range:
			var pz := _g_origin.y + z * _g_cell
			for x: int in x_range:
				var c := z * _g_w + x
				var px := _g_origin.x + x * _g_cell
				for nb: Vector2i in nbs:
					var nx := x + nb.x
					var nz := z + nb.y
					if nx < 0 or nz < 0 or nx >= _g_w or nz >= _g_h:
						continue
					var k := _g_idx[nz * _g_w + nx]
					if k < 0:
						continue
					var ddx := px - fx[k]
					var ddz := pz - fz[k]
					var d := sqrt(ddx * ddx + ddz * ddz)
					if d < _g_dist[c]:
						_g_dist[c] = d
						_g_idx[c] = k

	_g_height = PackedFloat32Array()
	_g_height.resize(total)
	var colors := PackedColorArray()
	colors.resize(total)
	for z in _g_h:
		var pz := _g_origin.y + z * _g_cell
		for x in _g_w:
			var c := z * _g_w + x
			var px := _g_origin.x + x * _g_cell
			var fr := frames[_g_idx[c]]
			var d := _g_dist[c]
			var rel := Vector3(px - fr.origin.x, 0.0, pz - fr.origin.z)
			var lat := clampf(rel.dot(fr.basis.x), -hw - 1.3, hw + 1.3)
			var road_y := fr.origin.y + fr.basis.x.y * lat
			var nh := _noise.get_noise_2d(px, pz) * float(theme.noise_amp)
			var hills := smoothstep(30.0, 170.0, d) * (float(theme.hill_base) + float(theme.hill_var) * (_noise_big.get_noise_2d(px, pz) + 0.5))
			var h: float
			if d < hw + 2.2:
				h = road_y - 0.5
			else:
				var t := smoothstep(hw + 2.2, hw + 40.0, d)
				h = lerpf(road_y - 0.12, road_y + nh + hills, t)
			_g_height[c] = h
			var dirt := 1.0 - smoothstep(hw + 2.0, hw + 5.5, d)
			dirt = maxf(dirt, smoothstep(0.32, 0.5, _noise.get_noise_2d(px * 2.3 + 91.0, pz * 2.3)) * 0.9)
			colors[c] = Color(dirt, 0, 0)

	var verts := PackedVector3Array()
	var normals := PackedVector3Array()
	verts.resize(total)
	normals.resize(total)
	for z in _g_h:
		for x in _g_w:
			var c := z * _g_w + x
			verts[c] = Vector3(_g_origin.x + x * _g_cell, _g_height[c], _g_origin.y + z * _g_cell)
			var hl := _g_height[z * _g_w + maxi(x - 1, 0)]
			var hr := _g_height[z * _g_w + mini(x + 1, _g_w - 1)]
			var hd := _g_height[maxi(z - 1, 0) * _g_w + x]
			var hu := _g_height[mini(z + 1, _g_h - 1) * _g_w + x]
			normals[c] = Vector3(hl - hr, 2.0 * _g_cell, hd - hu).normalized()
	var idx := PackedInt32Array()
	idx.resize((_g_w - 1) * (_g_h - 1) * 6)
	var ii := 0
	for z in _g_h - 1:
		for x in _g_w - 1:
			var a := z * _g_w + x
			var b := a + 1
			var c2 := a + _g_w
			var d2 := c2 + 1
			idx[ii] = a; idx[ii + 1] = b; idx[ii + 2] = d2
			idx[ii + 3] = a; idx[ii + 4] = d2; idx[ii + 5] = c2
			ii += 6
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var mat := ShaderMaterial.new()
	mat.shader = load("res://scripts/track/terrain.gdshader")
	for pair: Array in [["grass", theme.ground_a, theme.tint_a, theme.scale_a], ["dirt", theme.ground_b, theme.tint_b, theme.scale_b]]:
		var tp := tex_paths(pair[1])
		if ResourceLoader.exists(tp.albedo):
			mat.set_shader_parameter(pair[0] + "_albedo", load(tp.albedo))
			mat.set_shader_parameter(pair[0] + "_normal", load(tp.normal))
			mat.set_shader_parameter(pair[0] + "_arm", load(tp.arm))
		mat.set_shader_parameter(pair[0] + "_tint", pair[2])
		mat.set_shader_parameter(pair[0] + "_scale", pair[3])
	mesh.surface_set_material(0, mat)

	var body := StaticBody3D.new()
	body.name = "Terrain"
	body.collision_layer = Kart.LAYER_TRACK
	body.collision_mask = 0
	body.set_meta("surface", "grass")
	add_child(body)
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	body.add_child(mi)
	var cs := CollisionShape3D.new()
	cs.shape = mesh.create_trimesh_shape()
	body.add_child(cs)


## Rampa de terra com colisão da borda externa da zebra até o terreno. Sem ela havia um
## degrau de ~0,5 m na borda da pista e o kart que saía da zebra não conseguia voltar.
func _build_shoulders() -> void:
	const CURB_W := 1.3
	const LATS := [0.0, 0.9, 1.9, 3.2]
	const BLEND := [0.0, 0.45, 0.8, 1.0]
	var hw := road_width * 0.5
	var body := StaticBody3D.new()
	body.name = "Shoulders"
	body.collision_layer = Kart.LAYER_TRACK
	body.collision_mask = 0
	body.set_meta("surface", "grass")
	add_child(body)
	var mat := _tex_material(theme.ground_b, theme.tint_b)
	var count := frames.size()
	var nl := LATS.size()
	for side: float in [-1.0, 1.0]:
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		for i in count + 1:
			var fr := frames[i % count]
			var edge := fr.origin + fr.basis.x * side * (hw + CURB_W)
			var outward := Vector3(fr.basis.x.x, 0.0, fr.basis.x.z).normalized() * side
			for j in nl:
				var p := edge + outward * float(LATS[j])
				p.y = lerpf(edge.y, terrain_height(p.x, p.z) - 0.22, float(BLEND[j]))
				st.set_uv(Vector2(float(LATS[j]) / 3.0, i * _step / 4.0))
				st.add_vertex(p)
		for i in count:
			for j in nl - 1:
				var a := i * nl + j
				var b := a + 1
				var c := a + nl
				var d := c + 1
				if side > 0:
					st.add_index(a); st.add_index(c); st.add_index(d)
					st.add_index(a); st.add_index(d); st.add_index(b)
				else:
					st.add_index(a); st.add_index(d); st.add_index(c)
					st.add_index(a); st.add_index(b); st.add_index(d)
		st.generate_normals()
		st.generate_tangents()
		var mesh := st.commit()
		mesh.surface_set_material(0, mat)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		body.add_child(mi)
		var cs := CollisionShape3D.new()
		cs.shape = mesh.create_trimesh_shape()
		body.add_child(cs)


func _build_walls() -> void:
	var hw := road_width * 0.5
	var body := StaticBody3D.new()
	body.name = "Walls"
	body.collision_layer = Kart.LAYER_TRACK
	body.collision_mask = 0
	body.set_meta("surface", "wall")
	add_child(body)
	var rail_mat := StandardMaterial3D.new()
	rail_mat.albedo_color = theme.rail_color
	if (theme.rail_glow as Color).get_luminance() > 0.01:
		rail_mat.emission_enabled = true
		rail_mat.emission = theme.rail_glow
		rail_mat.emission_energy_multiplier = 2.2
	rail_mat.metallic = 0.85
	rail_mat.roughness = 0.32
	rail_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	var post_mesh := BoxMesh.new()
	post_mesh.size = Vector3(0.14, 1.1, 0.14)
	var post_mat := StandardMaterial3D.new()
	post_mat.albedo_color = Color(0.25, 0.26, 0.28)
	post_mat.metallic = 0.6
	post_mat.roughness = 0.5
	post_mesh.material = post_mat
	var count := frames.size()
	for side: float in [-1.0, 1.0]:
		var faces := PackedVector3Array()
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		var posts: Array[Transform3D] = []
		var pts: Array[Vector3] = []
		for i in count + 1:
			var fr := frames[i % count]
			var p := fr.origin + fr.basis.x * side * (hw + wall_distance)
			p.y = terrain_height(p.x, p.z)
			pts.append(p)
		for i in count:
			var a := pts[i]
			var b := pts[i + 1]
			var up := Vector3.UP
			var dir := (b - a).normalized()
			var nrm := dir.cross(Vector3.UP).normalized() * side
			# Parede de colisão: um pouco à frente do trilho (o kart é maior que a esfera de
			# colisão) e bem alta, para ninguém sair da pista num salto.
			var ca := a + nrm * 0.55
			var cb := b + nrm * 0.55
			faces.append_array(PackedVector3Array([ca - up, ca + up * WALL_HEIGHT, cb + up * WALL_HEIGHT, ca - up, cb + up * WALL_HEIGHT, cb - up]))
			var y0 := 0.45
			var y1 := 0.85
			var quads := [
				[a + up * y0 + nrm * 0.05, b + up * y0 + nrm * 0.05, b + up * y1 + nrm * 0.05, a + up * y1 + nrm * 0.05],
				[a + up * y1 + nrm * 0.05, b + up * y1 + nrm * 0.05, b + up * y1 - nrm * 0.12, a + up * y1 - nrm * 0.12],
				[a + up * (y0 + 0.2) + nrm * 0.1, b + up * (y0 + 0.2) + nrm * 0.1, b + up * (y0 + 0.2) - nrm * 0.0, a + up * (y0 + 0.2) - nrm * 0.0],
			]
			for q: Array in quads:
				_add_quad(st, q[0], q[1], q[2], q[3], side)
			if i % 2 == 0:
				posts.append(Transform3D(Basis(), a + up * 0.4 - nrm * 0.1))
		st.generate_normals()
		var rail := MeshInstance3D.new()
		rail.mesh = st.commit()
		rail.material_override = rail_mat
		add_child(rail)
		var shape := ConcavePolygonShape3D.new()
		shape.backface_collision = true
		shape.set_faces(faces)
		var cs := CollisionShape3D.new()
		cs.shape = shape
		body.add_child(cs)
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = post_mesh
		mm.instance_count = posts.size()
		for j in posts.size():
			mm.set_instance_transform(j, posts[j])
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		add_child(mmi)


func _add_quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, side: float) -> void:
	if side > 0:
		st.add_vertex(a); st.add_vertex(c); st.add_vertex(b)
		st.add_vertex(a); st.add_vertex(d); st.add_vertex(c)
	else:
		st.add_vertex(a); st.add_vertex(b); st.add_vertex(c)
		st.add_vertex(a); st.add_vertex(c); st.add_vertex(d)


func _build_start_line() -> void:
	var xf := sample(0.0)
	var img := Image.create(16, 2, false, Image.FORMAT_RGBA8)
	for x in 16:
		for y in 2:
			img.set_pixel(x, y, Color.WHITE if (x + y) % 2 == 0 else Color(0.05, 0.05, 0.05))
	var tex := ImageTexture.create_from_image(img)
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = tex
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	mat.roughness = 0.7
	var pm := PlaneMesh.new()
	pm.size = Vector2(road_width, road_width * 2.0 / 16.0)
	pm.material = mat
	var mi := MeshInstance3D.new()
	mi.mesh = pm
	mi.transform = Transform3D(xf.basis, xf.origin + xf.basis.y * 0.015)
	add_child(mi)
	var arch := place_prop("start_arch", xf, false)
	if arch == null:
		_fallback_arch(xf)


func _fallback_arch(xf: Transform3D) -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.15, 0.15, 0.18)
	mat.metallic = 0.7
	for side: float in [-1.0, 1.0]:
		var leg := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(0.6, 7.0, 0.6)
		bm.material = mat
		leg.mesh = bm
		leg.position = xf.origin + xf.basis.x * side * 9.5 + Vector3.UP * 3.5
		add_child(leg)
	var beam := MeshInstance3D.new()
	var b2 := BoxMesh.new()
	b2.size = Vector3(19.6, 1.6, 0.5)
	var bmat := StandardMaterial3D.new()
	bmat.albedo_color = Color(0.9, 0.2, 0.1)
	b2.material = bmat
	beam.mesh = b2
	beam.transform = Transform3D(Basis(xf.basis.x, Vector3.UP, xf.basis.x.cross(Vector3.UP)), xf.origin + Vector3.UP * 6.5)
	add_child(beam)


func add_item_row(offset: float, lanes := [-0.55, -0.18, 0.18, 0.55]) -> void:
	var xf := sample(offset)
	for l: float in lanes:
		var box := Area3D.new()
		box.set_script(ItemBoxScript)
		box.position = xf.origin + xf.basis.x * l * road_width * 0.5 + xf.basis.y * 1.0
		add_child(box)


func add_boost_pad(offset: float, lateral: float) -> void:
	var xf := sample(offset)
	var pad := Area3D.new()
	pad.set_script(BoostPadScript)
	pad.transform = Transform3D(xf.basis, xf.origin + xf.basis.x * lateral * road_width * 0.5 + xf.basis.y * 0.02)
	add_child(pad)


func add_ramp(offset: float, lateral: float, width := 6.0, ramp_len := 7.0, height := 1.5) -> void:
	_ramps.append([offset, lateral])
	var xf := sample(offset)
	var body := StaticBody3D.new()
	body.collision_layer = Kart.LAYER_TRACK
	body.collision_mask = 0
	body.set_meta("surface", "road")
	body.transform = Transform3D(xf.basis, xf.origin + xf.basis.x * lateral * road_width * 0.5)
	add_child(body)
	var hw := width * 0.5
	# Cunha: começa no chão (z = +len/2) e sobe até `height` (z = -len/2). Curva suave.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var steps := 10
	var prof: Array[Vector2] = [] # (z, y)
	for i in steps + 1:
		var t := float(i) / steps
		prof.append(Vector2(ramp_len * 0.5 - t * ramp_len, height * t * t * 0.6 + height * t * 0.4))
	for i in steps:
		var p0 := prof[i]
		var p1 := prof[i + 1]
		var a := Vector3(-hw, p0.y, p0.x)
		var b := Vector3(hw, p0.y, p0.x)
		var c := Vector3(-hw, p1.y, p1.x)
		var d := Vector3(hw, p1.y, p1.x)
		st.set_uv(Vector2(0, i)); st.add_vertex(a)
		st.set_uv(Vector2(0, i + 1)); st.add_vertex(c)
		st.set_uv(Vector2(1, i + 1)); st.add_vertex(d)
		st.set_uv(Vector2(0, i)); st.add_vertex(a)
		st.set_uv(Vector2(1, i + 1)); st.add_vertex(d)
		st.set_uv(Vector2(1, i)); st.add_vertex(b)
		for s: float in [-1.0, 1.0]:
			var x := s * hw
			var q0 := Vector3(x, 0, p0.x)
			var q1 := Vector3(x, 0, p1.x)
			var r0 := Vector3(x, p0.y, p0.x)
			var r1 := Vector3(x, p1.y, p1.x)
			if s > 0:
				st.add_vertex(q0); st.add_vertex(r1); st.add_vertex(r0)
				st.add_vertex(q0); st.add_vertex(q1); st.add_vertex(r1)
			else:
				st.add_vertex(q0); st.add_vertex(r0); st.add_vertex(r1)
				st.add_vertex(q0); st.add_vertex(r1); st.add_vertex(q1)
	var top := prof[steps]
	var e := [Vector3(-hw, 0, top.x), Vector3(hw, 0, top.x), Vector3(hw, top.y, top.x), Vector3(-hw, top.y, top.x)]
	st.add_vertex(e[0]); st.add_vertex(e[2]); st.add_vertex(e[1])
	st.add_vertex(e[0]); st.add_vertex(e[3]); st.add_vertex(e[2])
	st.generate_normals()
	var mesh := st.commit()
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = stripe_texture(Color(1.0, 0.75, 0.05), Color(0.08, 0.08, 0.09))
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	mat.uv1_scale = Vector3(1, 0.5, 1)
	mat.roughness = 0.5
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mesh.surface_set_material(0, mat)
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	body.add_child(mi)
	var cs := CollisionShape3D.new()
	cs.shape = mesh.create_trimesh_shape()
	body.add_child(cs)


func _decorate() -> void:
	_rng.seed = decoration_seed
	var hw := road_width * 0.5
	var edge := hw + wall_distance + 3.0
	for rule: Array in theme.scatter:
		var count := int(float(rule[1]) * decoration_density)
		var tr := random_ground_transforms(count, edge + float(rule[2]), float(rule[3]), rule[4], rule[5], rule[6])
		scatter(rule[0], tr, rule[7], 420.0 if rule[7] else 220.0, rule[8], true)
	# Props à beira da pista virados para os pilotos: [prop, espaçamento, distância extra].
	for rs: Array in theme.get("roadside", []):
		var xfs: Array[Transform3D] = []
		var n := int(length / float(rs[1]))
		for i in n:
			var xf := sample((i + 0.5) * float(rs[1]))
			var side := 1.0 if i % 2 == 0 else -1.0
			var p := xf.origin + xf.basis.x * side * (hw + wall_distance + float(rs[2]))
			p.y = terrain_height(p.x, p.z)
			if p.y < liquid_y + 0.5:
				continue
			var face := -xf.basis.x * side
			face.y = 0.0
			face = face.normalized()
			xfs.append(Transform3D(Basis(Vector3.UP.cross(face), Vector3.UP, face), p))
		scatter(rs[0], xfs, true, 350.0, {}, true)
	if theme.has("city"):
		_build_city(theme.city)
	if not theme.start_props:
		return
	var tires: Array[Transform3D] = []
	for i in range(0, frames.size(), 4):
		if absf(banks[i]) > 0.11:
			var side := -signf(banks[i])
			var p := frames[i].origin + frames[i].basis.x * side * (hw + wall_distance + 1.2)
			p.y = terrain_height(p.x, p.z)
			if p.y > liquid_y:
				tires.append(Transform3D(Basis(Vector3.UP, _rng.randf() * TAU), p))
	scatter("tire_stack", tires, true, 300.0)
	var flags: Array[Transform3D] = []
	for i in range(0, frames.size(), 12):
		var off := i * _step
		if off < 110.0 or off > length - 60.0:
			for side: float in [-1.0, 1.0]:
				var p := frames[i].origin + frames[i].basis.x * side * (hw + wall_distance + 2.0)
				p.y = terrain_height(p.x, p.z)
				if p.y > liquid_y:
					flags.append(Transform3D(Basis(Vector3.UP, _rng.randf() * TAU), p))
	scatter("flag_pole", flags, true, 300.0)
	for off: float in [40.0, length - 30.0]:
		var gxf := sample(off)
		var gpos := gxf.origin - gxf.basis.x * (hw + wall_distance + 9.0)
		gpos.y = terrain_height(gpos.x, gpos.z)
		var to_track := gxf.basis.x
		to_track.y = 0.0
		to_track = to_track.normalized()
		if gpos.y > liquid_y:
			place_prop("grandstand", Transform3D(Basis(Vector3.UP.cross(to_track), Vector3.UP, to_track), gpos))
	var cones: Array[Transform3D] = []
	for r: Array in _ramps:
		for j in 4:
			var cx := sample(float(r[0]) - 6.0 + j * 2.5)
			cones.append(Transform3D(Basis(), cx.origin + cx.basis.x * (float(r[1]) - 0.26) * road_width * 0.5 + cx.basis.y * 0.02))
	scatter("traffic_cone", cones, true, 200.0)


## Cidade: quarteirões de prédios ladeando a pista (como uma avenida), com alturas e
## cores variadas. cfg: {prop, spacing, setback, height: [min, max], tints: [{material: cor}...]}
func _build_city(cfg: Dictionary) -> void:
	var hw := road_width * 0.5
	var prop: String = cfg.get("prop", "building_block")
	var spacing: float = cfg.get("spacing", 15.0) * (2.0 if Settings.is_mobile() else 1.0)
	var setback: float = cfg.get("setback", 9.5)
	var hmin: float = cfg.get("height", [0.7, 2.0])[0]
	var hmax: float = cfg.get("height", [0.7, 2.0])[1]
	var tints: Array = cfg.get("tints", [{}])
	var half := 6.0
	var clear := hw + wall_distance + 2.5
	var groups: Array = []
	for i in tints.size():
		groups.append([] as Array[Transform3D])
	var placed: Array[Vector2] = []
	var n := int(length / spacing)
	for i in n:
		for side: float in [-1.0, 1.0]:
			var off := i * spacing + (0.0 if side > 0 else spacing * 0.5)
			if theme.start_props and side < 0 and (off < 75.0 or off > length - 60.0):
				continue
			var xf := sample(off)
			var w := _rng.randf_range(0.85, 1.2)
			var dist := hw + wall_distance + setback + (w - 1.0) * half + _rng.randf_range(0.0, 4.0)
			var p := xf.origin + xf.basis.x * side * dist
			var face := -xf.basis.x * side
			face.y = 0.0
			face = face.normalized()
			var right := Vector3.UP.cross(face)
			var ok := distance_to_road(p.x, p.z) > clear + half * w * 0.6
			for c: Vector2 in [Vector2(-1, -1), Vector2(1, -1), Vector2(-1, 1), Vector2(1, 1)]:
				var q := p + right * c.x * half * w + face * c.y * half * w
				if distance_to_road(q.x, q.z) < clear:
					ok = false
			var p2 := Vector2(p.x, p.z)
			for o: Vector2 in placed:
				if o.distance_to(p2) < half * 2.0 * w:
					ok = false
					break
			if not ok:
				continue
			placed.append(p2)
			p.y = terrain_height(p.x, p.z)
			var h := _rng.randf_range(hmin, hmax)
			var b := Basis(right * w, Vector3.UP * h, face * w) # base destra (espelhar inverte as faces)
			groups[_rng.randi() % groups.size()].append(Transform3D(b, p))
	for i in groups.size():
		scatter(prop, groups[i], true, 600.0, tints[i], true)


func _setup_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var hdri := TEX + "sky/%s_2k.hdr" % theme.sky
	if ResourceLoader.exists(hdri):
		var psm := PanoramaSkyMaterial.new()
		psm.panorama = load(hdri)
		psm.energy_multiplier = float(theme.sky_energy)
		sky.sky_material = psm
	else:
		sky.sky_material = ProceduralSkyMaterial.new()
	sky.radiance_size = Sky.RADIANCE_SIZE_64 if Settings.is_mobile() else Sky.RADIANCE_SIZE_256
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = float(theme.ambient)
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = float(theme.exposure)
	env.tonemap_white = 6.0
	env.glow_enabled = true
	env.glow_intensity = float(theme.glow)
	env.glow_bloom = 0.04
	env.glow_hdr_threshold = 1.1
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	env.ssao_enabled = true
	env.ssao_radius = 1.2
	env.ssao_intensity = 1.6
	env.fog_enabled = true
	env.fog_light_color = theme.fog_color
	env.fog_density = float(theme.fog_density)
	env.fog_aerial_perspective = float(theme.fog_aerial)
	env.fog_sky_affect = 0.0
	env.adjustment_enabled = true
	env.adjustment_saturation = float(theme.saturation)
	env.adjustment_contrast = float(theme.contrast)
	Settings.apply_environment(env)
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	sun.light_color = theme.sun_color
	sun.light_energy = float(theme.sun_energy)
	sun.shadow_enabled = true
	sun.shadow_blur = 1.2
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = 220.0
	sun.rotation_degrees = Vector3(float(theme.sun_pitch), float(theme.sun_yaw), 0.0)
	Settings.apply_sun(sun)
	add_child(sun)


func _build_liquid() -> void:
	if theme.liquid == "":
		return
	var min_y := INF
	for fr in frames:
		min_y = minf(min_y, fr.origin.y)
	liquid_y = min_y + float(theme.liquid_level)
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2((_g_w + 200) * _g_cell, (_g_h + 200) * _g_cell)
	var mat := ShaderMaterial.new()
	mat.shader = load("res://scripts/track/%s.gdshader" % theme.liquid)
	pm.material = mat
	mi.mesh = pm
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.position = Vector3(_g_origin.x + _g_w * _g_cell * 0.5, liquid_y, _g_origin.y + _g_h * _g_cell * 0.5)
	add_child(mi)


func _build_lamps() -> void:
	if not theme.lamps:
		return
	var hw := road_width * 0.5
	var spacing: float = theme.get("lamp_spacing", 42.0) * (1.8 if Settings.is_mobile() else 1.0)
	var count := int(length / spacing)
	var lamp_xfs: Array[Transform3D] = []
	for i in count:
		var off := i * spacing
		var xf := sample(off)
		var side := 1.0 if i % 2 == 0 else -1.0
		var p := xf.origin + xf.basis.x * side * (hw + wall_distance + 1.0)
		p.y = terrain_height(p.x, p.z)
		var to_track := -xf.basis.x * side
		to_track.y = 0.0
		to_track = to_track.normalized()
		# O braço do poste aponta para +X local: alinhamos +X com a direção da pista.
		lamp_xfs.append(Transform3D(Basis(to_track, Vector3.UP, to_track.cross(Vector3.UP)), p))
		var light := OmniLight3D.new()
		light.light_color = Color(1.0, 0.86, 0.66)
		light.light_energy = 7.0
		light.omni_range = 30.0
		light.omni_attenuation = 1.4
		light.shadow_enabled = false
		light.position = xf.origin + xf.basis.x * side * (hw - 1.0) + Vector3.UP * 6.5
		add_child(light)
	if ResourceLoader.exists(PROPS + "street_lamp.glb"):
		scatter("street_lamp", lamp_xfs, true, 350.0)
	else:
		var pole := CylinderMesh.new()
		pole.top_radius = 0.09
		pole.bottom_radius = 0.12
		pole.height = 6.5
		var pmat := StandardMaterial3D.new()
		pmat.albedo_color = Color(0.2, 0.2, 0.22)
		pmat.metallic = 0.8
		pole.material = pmat
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = pole
		mm.instance_count = lamp_xfs.size()
		for j in lamp_xfs.size():
			mm.set_instance_transform(j, lamp_xfs[j].translated(Vector3.UP * 3.25))
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		add_child(mmi)


## O importador glTF às vezes deixa de ativar as cores de vértice em algum material
## (visto no primeiro material de cada malha). Os props usam materiais brancos + COLOR_0,
## então ativamos sempre que a superfície tiver cores de vértice.
static func fix_vertex_colors(mesh: Mesh) -> void:
	if mesh == null or not mesh is ArrayMesh:
		return
	for i in mesh.get_surface_count():
		var m := mesh.surface_get_material(i) as BaseMaterial3D
		if m and not m.vertex_color_use_as_albedo and ((mesh as ArrayMesh).surface_get_format(i) & Mesh.ARRAY_FORMAT_COLOR) != 0:
			m.vertex_color_use_as_albedo = true


static func _tinted_mesh(mesh: Mesh, tints: Dictionary) -> Mesh:
	var copy: Mesh = mesh.duplicate()
	for i in copy.get_surface_count():
		var m := copy.surface_get_material(i)
		if m == null:
			continue
		var key := m.resource_name.to_lower()
		if tints.has(key) and m is BaseMaterial3D:
			var nm := (m as BaseMaterial3D).duplicate() as BaseMaterial3D
			nm.albedo_color = nm.albedo_color * (tints[key] as Color)
			copy.surface_set_material(i, nm)
	return copy


func place_prop(prop: String, xf: Transform3D, align_to_basis := true) -> Node3D:
	var path := PROPS + prop + ".glb"
	if not ResourceLoader.exists(path):
		return null
	var node: Node3D = (load(path) as PackedScene).instantiate()
	for mi: MeshInstance3D in node.find_children("*", "MeshInstance3D", true, false):
		fix_vertex_colors(mi.mesh)
	if align_to_basis:
		node.transform = xf
	else:
		var fwd := -xf.basis.z
		fwd.y = 0.0
		fwd = fwd.normalized()
		var right := fwd.cross(Vector3.UP)
		node.transform = Transform3D(Basis(right, Vector3.UP, -fwd), xf.origin)
	add_child(node)
	return node


func scatter(prop: String, transforms: Array[Transform3D], cast_shadows := true, vis_range := 420.0, tints := {}, ground_snap := false) -> void:
	var path := PROPS + prop + ".glb"
	if transforms.is_empty() or not ResourceLoader.exists(path):
		return
	var root: Node3D = (load(path) as PackedScene).instantiate()
	var parts: Array = []
	for mi: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		var rel := Transform3D.IDENTITY
		var n: Node = mi
		while n != root and n is Node3D:
			rel = (n as Node3D).transform * rel
			n = n.get_parent()
		var mesh: Mesh = mi.mesh
		fix_vertex_colors(mesh)
		if not tints.is_empty():
			mesh = _tinted_mesh(mesh, tints)
		parts.append([mesh, rel])
	root.free()
	if ground_snap:
		var box := AABB()
		for k in parts.size():
			var pa: Array = parts[k]
			var bb: AABB = (pa[1] as Transform3D) * (pa[0] as Mesh).get_aabb()
			box = bb if k == 0 else box.merge(bb)
		var r := maxf(box.size.x, box.size.z) * 0.5 * 0.85
		var snapped: Array[Transform3D] = []
		for t in transforms:
			snapped.append(_snap_to_ground(t, r))
		transforms = snapped
	var chunk := 110.0
	var buckets := {}
	for t in transforms:
		var key := Vector2i(floori(t.origin.x / chunk), floori(t.origin.z / chunk))
		if not buckets.has(key):
			buckets[key] = []
		buckets[key].append(t)
	for key: Vector2i in buckets:
		var list: Array = buckets[key]
		for part: Array in parts:
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = part[0]
			mm.instance_count = list.size()
			for j in list.size():
				mm.set_instance_transform(j, (list[j] as Transform3D) * (part[1] as Transform3D))
			var mmi := MultiMeshInstance3D.new()
			mmi.multimesh = mm
			mmi.visibility_range_end = vis_range * Settings.view_distance()
			mmi.visibility_range_end_margin = 20.0
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if cast_shadows and Settings.prop_shadows() else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(mmi)


func _snap_to_ground(t: Transform3D, base_radius: float) -> Transform3D:
	var sc := t.basis.get_scale()
	var r := base_radius * maxf(sc.x, sc.z)
	var low := terrain_height(t.origin.x, t.origin.z)
	if r > 0.4:
		for i in 8:
			var a := TAU * i / 8.0
			low = minf(low, terrain_height(t.origin.x + cos(a) * r, t.origin.z + sin(a) * r))
			low = minf(low, terrain_height(t.origin.x + cos(a) * r * 0.5, t.origin.z + sin(a) * r * 0.5))
	t.origin.y = minf(t.origin.y, low - 0.12)
	return t


func random_ground_transforms(count: int, min_d: float, max_d: float, scale_min: float, scale_max: float, cluster := 0.0) -> Array[Transform3D]:
	var out: Array[Transform3D] = []
	var tries := 0
	var size := Vector2((_g_w - 1) * _g_cell, (_g_h - 1) * _g_cell)
	while out.size() < count and tries < count * 40:
		tries += 1
		var x := _g_origin.x + _rng.randf() * size.x
		var z := _g_origin.y + _rng.randf() * size.y
		var d := distance_to_road(x, z)
		if d < min_d or d > max_d:
			continue
		if cluster > 0.0 and _noise.get_noise_2d(x * 0.5, z * 0.5) < cluster - 0.5:
			continue
		var gy := terrain_height(x, z)
		if gy < liquid_y + 0.5:
			continue
		var s := _rng.randf_range(scale_min, scale_max)
		var b := Basis(Vector3.UP, _rng.randf() * TAU).scaled(Vector3(s, s * _rng.randf_range(0.9, 1.15), s))
		out.append(Transform3D(b, Vector3(x, gy - 0.15, z)))
	return out
