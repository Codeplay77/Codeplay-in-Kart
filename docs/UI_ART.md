# Arte da interface e build

A interface usa grafite/azul, laranja para ações principais e azul-claro para foco
e informações secundárias. Os desenhos SVG são originais do projeto, sob CC0 1.0.

- `assets/ui/icons/`: navegação, controles e itens (turbo, orbe, mina).
- `assets/ui/landscapes/`: nove ilustrações por tema. São artes conceituais;
  o desenho ao lado mostra o traçado real de cada pista.
- `assets/ui/menu_overlay.svg`: moldura, faixas e gradientes do menu.
- `icon.svg`: ícone principal editável; `assets/ui/app_icon.png` e `.ico` são derivados.
- `scripts/ui/ui_theme.gd`: estilos, fontes, cores e helpers comuns.

## Regerar

Na raiz do projeto, com Godot no PATH:

```powershell
python tools/ui/generate_art.py
godot --headless --path . --script tools/ui/rasterize_icon.gd
python tools/ui/build_icons.py
godot --headless --path . --editor --import
```

O último script Python requer Pillow (`python -m pip install Pillow`). Os assets
prontos são versionados; nada precisa ser instalado para jogar ou exportar.

## Exportar para Windows

Instale os templates de exportação da mesma versão do Godot e execute:

```powershell
godot --headless --path . --export-release "Windows Desktop"
```

`export_presets.cfg` é versionado, exporta todos os recursos e inclui explicitamente
as artes da UI carregadas por caminho. O ícone `.ico` está configurado no projeto,
no executável e no wrapper de console. A saída é
`build/windows/CodeplayInKart.exe`, com o PCK embutido.
