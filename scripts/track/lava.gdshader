shader_type spatial;
render_mode cull_back;

uniform vec3 crust : source_color = vec3(0.07, 0.035, 0.03);
uniform vec3 hot : source_color = vec3(1.0, 0.36, 0.04);
uniform vec3 white_hot : source_color = vec3(1.0, 0.85, 0.35);
uniform float glow = 5.0;

varying vec3 wpos;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) {
	float v = 0.0; float a = 0.5;
	for (int i = 0; i < 5; i++) { v += noise(p) * a; p *= 2.07; a *= 0.5; }
	return v;
}

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = wpos.xz * 0.05;
	float t = TIME * 0.04;
	vec2 warp = vec2(fbm(p + vec2(t, 0.0)), fbm(p + vec2(0.0, -t) + 5.2));
	float n = fbm(p * 1.6 + warp * 1.8 + vec2(t * 0.5));
	float veins = smoothstep(0.42, 0.62, n);
	float core = smoothstep(0.6, 0.75, n);
	float pulse = 0.8 + 0.2 * sin(TIME * 1.3 + n * 12.0);
	vec3 emiss = mix(hot, white_hot, core) * veins * glow * pulse;
	ALBEDO = mix(crust, hot * 0.4, veins);
	EMISSION = emiss;
	ROUGHNESS = mix(0.9, 0.4, veins);
	METALLIC = 0.0;
}
