shader_type spatial;
render_mode unshaded, cull_disabled, blend_mix, depth_draw_opaque;
// PlaneMesh: UV.y cresce para +Z local e a pista anda para -Z, então a ponta das setas fica em UV.y menor.

uniform vec4 color_a : source_color = vec4(1.0, 0.55, 0.05, 1.0);
uniform vec4 color_b : source_color = vec4(1.0, 0.95, 0.3, 1.0);
uniform float speed = 1.6;
uniform float glow = 2.6;

void fragment() {
	vec2 uv = UV;
	float y = fract(uv.y * 3.0 + TIME * speed);
	float x = abs(uv.x - 0.5);
	float chevron = step(fract(y - x * 1.2), 0.45);
	float border = step(0.44, x);
	vec3 c = mix(color_a.rgb, color_b.rgb, chevron);
	c = mix(c, vec3(0.05), border * 0.85);
	ALBEDO = c * mix(1.0, glow, chevron * (1.0 - border));
	ALPHA = 1.0;
}
