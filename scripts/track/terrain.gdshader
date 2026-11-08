shader_type spatial;
// Terreno: mistura grama e terra usando COLOR.r (pintado pelo gerador da pista).

uniform sampler2D grass_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_arm : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_arm : filter_linear_mipmap_anisotropic, repeat_enable;
uniform float grass_scale = 0.16;
uniform float dirt_scale = 0.2;
uniform vec3 grass_tint : source_color = vec3(0.62, 0.9, 0.42);
uniform vec3 dirt_tint : source_color = vec3(1.0, 0.92, 0.82);

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}

void fragment() {
	vec2 uv_g = world_pos.xz * grass_scale;
	vec2 uv_g2 = world_pos.xz * grass_scale * 0.31 + vec2(0.37, 0.71);
	vec2 uv_d = world_pos.xz * dirt_scale;
	float macro = vnoise(world_pos.xz * 0.03);
	vec3 g = mix(texture(grass_albedo, uv_g).rgb, texture(grass_albedo, uv_g2).rgb, 0.35) * grass_tint;
	g *= mix(0.82, 1.12, macro);
	vec3 d = texture(dirt_albedo, uv_d).rgb * dirt_tint;
	float noise_edge = vnoise(world_pos.xz * 0.35) * 0.35;
	float t = smoothstep(0.35, 0.65, COLOR.r + noise_edge - 0.17);
	vec3 arm = mix(texture(grass_arm, uv_g).rgb, texture(dirt_arm, uv_d).rgb, t);
	ALBEDO = mix(g, d, t);
	AO = arm.r;
	AO_LIGHT_AFFECT = 0.4;
	ROUGHNESS = clamp(arm.g, 0.5, 1.0);
	METALLIC = 0.0;
	NORMAL_MAP = mix(texture(grass_normal, uv_g).rgb, texture(dirt_normal, uv_d).rgb, t);
	NORMAL_MAP_DEPTH = 1.0;
}
