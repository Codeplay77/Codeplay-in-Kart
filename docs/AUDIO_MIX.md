# Revisão de áudio

Os originais em `assets/audio/sfx/` e as músicas foram preservados. A versão nova
prioriza `assets/audio/refined/`: 30 arquivos WAV com importação PCM sem perdas.
Os loops gravados continuam em 44,1 kHz; os novos sinais de itens, voltas e largada
são sintetizados em 48 kHz. Converter para WAV evita outra compressão com perdas;
não recupera detalhe ausente das gravações de origem.

## Alterações no jogo

- Motores dos adversários mais discretos e com alcance menor; o motor do jogador
  mantém destaque, com transições de volume e pitch suavizadas.
- Trocas de marcha com histerese e intervalo mínimo, evitando alternância constante
  quando a velocidade oscila perto do ponto de troca.
- Menos aspereza nos médios/agudos dos motores e pneus. Os filtros dos loops
  trabalham com sinal periódico para não criar transientes de inicialização.
- Efeitos curtos com ataque e saída suaves; colisões repetidas têm intervalo mínimo.
- Música com margem para os efeitos; removido o ganho positivo nas faixas com picos altos.
- Compressão leve nos grupos Engine e SFX; limitador final a -1,5 dB.
- Parar a música durante uma transição agora encerra os dois players.
- Música e vinhetas têm ganho individual medido por loudness e true peak;
  objetivo de -20 LUFS, limitado por teto de -3 dBTP e sem ganho positivo.
  O ajuste é feito na reprodução, preservando o estéreo e evitando recompressão.
- Transições entre faixas usam curvas de potência constante em amplitude, evitando
  a queda brusca de volume no meio da troca do menu para a corrida.
- Volumes salvos pelo jogador são respeitados.

## Regerar

Requer Python com numpy/scipy e FFmpeg para gerar os assets; jogar/exportar usa os
arquivos prontos. Com Godot no PATH, execute na raiz:

```powershell
python tools/audio/refine_audio.py
python tools/audio/measure_music.py
godot --headless --path . --editor --import
godot --headless --path . --export-release "Windows Desktop"
```

`docs/audio_processing.json` contém taxa, duração, pico e RMS dos assets gerados.
`docs/music_levels.json` documenta as medições das músicas e os ganhos gerados em
`scripts/audio/music_levels.gd`, incluído no jogo por referência direta.

O preset Windows exporta todos os recursos e inclui explicitamente os novos WAV.
