shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_back, specular_schlick_ggx;

uniform vec3 deep_color : source_color = vec3(0.02, 0.22, 0.38);
uniform vec3 shallow_color : source_color = vec3(0.1, 0.62, 0.68);
uniform vec3 foam_color : source_color = vec3(0.95, 0.98, 1.0);
uniform float wave_scale = 0.06;
uniform float wave_speed = 0.35;
uniform sampler2D depth_tex : hint_depth_texture, filter_linear_mipmap;

varying vec3 wpos;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float waves(vec2 p, float t) {
	return noise(p * 1.0 + vec2(t, t * 0.6)) * 0.5 + noise(p * 2.3 - vec2(t * 0.8, t * 1.1)) * 0.3 + noise(p * 5.1 + vec2(t * 1.7, -t)) * 0.2;
}

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = wpos.xz * wave_scale;
	float t = TIME * wave_speed;
	float e = 0.05;
	float h = waves(p, t);
	float hx = waves(p + vec2(e, 0.0), t);
	float hz = waves(p + vec2(0.0, e), t);
	vec3 n_world = normalize(vec3((h - hx) * 2.2, 1.0, (h - hz) * 2.2));
	NORMAL = normalize((VIEW_MATRIX * vec4(n_world, 0.0)).xyz);

	float depth = textureLod(depth_tex, SCREEN_UV, 0.0).r;
	vec4 ndc = vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0);
	vec4 view = INV_PROJECTION_MATRIX * ndc;
	view.xyz /= view.w;
	float water_depth = clamp(-view.z + VERTEX.z, 0.0, 50.0);
	float shallow = exp(-water_depth * 0.35);
	float foam = smoothstep(0.55, 1.0, shallow) * smoothstep(0.3, 0.7, noise(wpos.xz * 0.8 + TIME * 0.4));
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 4.0);
	vec3 col = mix(deep_color, shallow_color, shallow);
	col = mix(col, foam_color, foam * 0.8);
	ALBEDO = col;
	ROUGHNESS = 0.06;
	METALLIC = 0.0;
	SPECULAR = 0.6;
	ALPHA = clamp(0.62 + fres * 0.35 + foam * 0.3 - shallow * 0.35, 0.25, 0.97);
}
