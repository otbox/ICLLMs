# Capturador de UI — LibreOffice (Windows)

Extrai a árvore de componentes de aplicações Windows via **pywinauto** (UI Automation), com screenshots opcionais e banlist de ruído.

Guia completo de configuração e formato JSON: **[HOWUSE.md](./HOWUSE.md)**.

---

## Script

### `teste.py`

| Peça | Função |
|------|--------|
| `BanlistConfig` | Ignora nomes exatos, classes e substrings |
| `ExtractorConfig` | Path do `.exe`, output, multithreading, screenshots, profundidade |
| `UIExtractor` | Conecta ao app, processa árvore, expande menus, grava JSON |

**Entry point** (final do arquivo): ajuste `app_path` (ex. LibreOffice Writer), banlist e flags `use_multithreading` / `take_screenshots`.

```bash
pip install -r ../requirementsWindows.txt
python teste.py
```

**Saídas padrão:**

- `resultado_libreoffice_avancado.json` (ou nome em `output_file`)
- Pasta de imagens (ex. `imgs_lo_avancado/`)
- Log: `extrator.log`

Arquivos `resultado_libreoffice_avancado1.json` / `2.json` nesta pasta são exemplos de runs anteriores.

**SO:** Windows 10/11 apenas.
