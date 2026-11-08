# Contrato de Assets — Codeplay in Kart

Este documento define as convenções que todo modelo 3D precisa seguir para funcionar
no jogo. O código do Godot depende **exatamente** destes nomes.

Todos os modelos são gerados por scripts Python do Blender em `tools/blender/`, para que
qualquer pessoa possa reproduzir, editar e criar novas peças.

## Unidades e eixos

- Unidade: **metros**. Escala real de kart (≈ 2.0 m de comprimento).
- No Blender: **Z para cima, frente do kart apontando para +Y**.
  (O exportador glTF converte para Y-up; no Godot a frente vira -Z, que é o padrão do engine.)
- Formato de exportação: `.glb` (glTF binário), modificadores aplicados, normais exportadas.

## Peças do kart (`assets/models/karts/`)

| Arquivo | Conteúdo |
|---|---|
| `body_<id>.glb` | Carroceria/chassi completo (assento, volante, motor, para-choques...) |
| `wheel_<id>.glb` | Uma roda (pneu + aro + cubo) |
| `spoiler_<id>.glb` | Aerofólio traseiro |
| `driver.glb` | Piloto sentado (capacete, macacão, luvas) |

### Carroceria (`body_*.glb`)

- Origem: no **chão** (Z=0), no centro do kart (meio do entre-eixos, centro lateral).
- Deve conter estes **Empties** (exportados como `Node3D`), com nomes exatos:
  - `socket_wheel_fl`, `socket_wheel_fr`, `socket_wheel_rl`, `socket_wheel_rr` — centro do eixo de cada roda.
    A **escala** (uniforme) do empty define o tamanho da roda naquele eixo
    (roda nominal tem raio 0.28 m; escala 0.9 ⇒ raio 0.252 m ⇒ o empty deve estar em Z = 0.252).
    Rotação: identidade.
  - `socket_spoiler` — ponto de montagem do aerofólio (rotação identidade).
  - `socket_driver` — quadril do piloto (rotação identidade).
  - `socket_exhaust_l`, `socket_exhaust_r` — ponta dos escapamentos (para partículas de fogo/turbo).
- Objeto `steering_wheel`: o volante, separado, com origem no cubo do volante e o
  **eixo Y local** apontando ao longo da coluna de direção (para frente/baixo, saindo do piloto).
  O jogo gira o volante em torno desse eixo.
- O volante deve ficar em `socket_driver + (0, 0.42, 0.24)` (em metros, Blender) para que as mãos
  do piloto padrão alcancem.

### Roda (`wheel_*.glb`)

- Origem no centro do eixo. Eixo de rotação ao longo de **X**. Raio nominal **0.28 m**, largura ~0.24 m.
- A face externa (aro visível) aponta para **+X** (lado direito). O jogo espelha para as rodas esquerdas.

### Aerofólio (`spoiler_*.glb`)

- Origem no ponto de montagem (base dos suportes); a asa sobe/vai para trás a partir dele.

### Piloto (`driver.glb`)

- Origem no quadril, sentado, olhando para +Y, mãos em `(±0.17, 0.42, 0.24)` (posição do volante).
- Objeto `driver_head` separado (capacete), com origem no pescoço — o jogo inclina a cabeça nas curvas.

## Materiais recoloríveis

O jogo troca a cor de materiais pelo **nome** (prefixo). Nomes exatos:

| Material | Uso | Customizável |
|---|---|---|
| `paint_primary` | Pintura principal | ✅ |
| `paint_secondary` | Pintura secundária / faixas | ✅ |
| `paint_accent` | Detalhes de destaque | ✅ |
| `rim` | Aro das rodas | ✅ |
| `suit` | Macacão do piloto | ✅ |
| `helmet` | Capacete | ✅ |
| `chrome`, `carbon`, `metal_dark`, `rubber`, `seat_fabric`, `glass`, `visor`, `glove` | Fixos | ❌ |
| `whitewall` | Faixa branca do pneu (roda `retro`) | ❌ |
| `emissive_light`, `emissive_tail` | Faróis / lanternas (emissivos) | ❌ |

Use apenas valores escalares do Principled BSDF (cor base, metálico, rugosidade, emissão,
clearcoat) — texturas procedurais do Blender não são exportadas para glTF.
