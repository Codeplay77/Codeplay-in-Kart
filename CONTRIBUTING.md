# Como contribuir

Obrigado por querer ajudar o **Codeplay in Kart**! 🏎️

## Fluxo

1. Faça um fork e crie um branch: `git checkout -b minha-feature`.
2. Faça suas alterações e teste no Godot (F5).
3. Abra um Pull Request descrevendo o que mudou e, se for visual, com um screenshot.

## Convenções de código (GDScript)

- Godot 4.7, GDScript com **tipagem estática** sempre que possível.
- Tabs para indentação; `snake_case` para funções/variáveis; `PascalCase` para classes.
- Comentários e textos da interface em **português**; nomes de código podem ser em inglês.
- Comente apenas o que o código não deixa claro: formatos de dados, unidades e o motivo de decisões.
- Prefira gerar nós em código ou cenas simples — evita conflitos de merge em `.tscn`.

## Modelos 3D

- Todo modelo deve ser gerado por um script em `tools/blender/` (nada de `.blend` solto),
  para que qualquer pessoa consiga reproduzir e ajustar.
- Siga o [contrato de assets](docs/ASSET_CONTRACT.md): nomes de sockets, materiais e eixos.
- Respeite os orçamentos de polígonos (8 karts na tela em GPUs medianas).

## Versionamento

O projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/): `MAIOR.MENOR.CORREÇÃO`.
Registre cada mudança relevante no [CHANGELOG](CHANGELOG.md). Ao lançar uma versão, atualize:

- `project.godot`: `config/version` (é o número exibido no menu do jogo);
- `export_presets.cfg`: `application/file_version`, `application/product_version`,
  `version/name` e some 1 em `version/code` (exigência do Android);
- o selo de versão no início do `README.md`.

## Licença das contribuições

Ao enviar uma contribuição, você concorda em publicá-la sob a [CC0 1.0](LICENSE).

## Recursos de terceiros

Apenas recursos CC0. Registre tudo em `CREDITS.md`.

## Ideias de primeiras contribuições

Veja o *Roadmap* no README: novas pistas, novos itens, peças de kart, sons.
