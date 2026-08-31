# Extrações — datasets brutos

Pasta de saída e material intermediário das capturas de UI.

---

## Script

### `ContadorDeComponents.py`

Conta nós em JSONs no formato de **extração Selenium/pywinauto**:

- Raiz esperada: chave `ui_structure`
- Cada `dict` na árvore conta 1; filhos em `filhos` entram na recursão
- `build_folder_report(pasta)` varre `*.json` recursivamente

```bash
# Em extracoes/, ajuste o nome da pasta no __main__ (ex.: "limeira", "americanas")
python ContadorDeComponents.py
```

Gera `relatorio_componentes_ui_structure.json`.

> Para contar inventários gerados por LLM (`id` + `type`), use  
> `../AnalisysLLMs_System/results/ContadorDeComponents.py`.

---

## Subpastas

| Pasta | Conteúdo típico |
|-------|-----------------|
| `americanas/` | `estrutura_ui.json` por página, HTML reconstruído, assets Wayback, relatórios |
| `limeira/` | Estruturas por seção do portal (cultura, notícias, transparência, …) |
| `libreoffice/` | Cópia do extrator Windows + JSONs de resultado |

Cada página costuma ter `estrutura_ui.json` e, quando gerado, pasta `screenshots_ui/`.
