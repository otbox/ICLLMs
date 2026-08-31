# Modelos — comparação via OpenRouter

Scripts CLI para enviar a **mesma pergunta** a várias LLMs (texto e, em evolução, multimodal), usando JSON de extração de UI como contexto, e comparar qualidade do “próximo passo”.

Documentação da API multimodal:  
https://openrouter.ai/docs/guides/overview/multimodal/images

---

## Pré-requisito

Na raiz do ICLLMs (ou nesta pasta), `.env`:

```env
OPENROUTER_API_KEY=sua_chave
```

```bash
pip install openai python-dotenv
```

---

## Scripts

### `main.py`

Protótipo de chat interativo com system prompt de guia de tarefas.

| Comando | Efeito |
|---------|--------|
| texto livre | Envia ao modelo |
| `file:<caminho>` | (hook incompleto) |
| `history` | Mostra histórico |
| `clear` | Limpa histórico |
| `exit` | Sai |

Limitação: lista `MODELS` com placeholders; threading não finalizado. Preferir `main2.py`.

```bash
python main.py
```

### `main2.py`

Comparação multi-modelo com contexto JSON opcional.

**Funções:**

| Função | Descrição |
|--------|-----------|
| `query_model_with_messages` | Uma chamada OpenRouter; retorna status, duração, tokens |
| `compare_models_with_context` | Dispara N modelos (paralelo ou sequencial); grava `.txt` + `*_summary.json` em `model_responses/` |
| `interactive_comparison_with_context` | Wizard no terminal (JSON colado/arquivo, seleção de modelos, pergunta) |
| `exemplo_com_contexto` | Run automático com path hardcoded — **ajuste o caminho** do JSON antes de usar |

No `__main__`, descomente o modo desejado.

```bash
python main2.py
```

Saída típica em `model_responses/`:

```
YYYYMMDD_HHMMSS_<modelo>.txt
YYYYMMDD_HHMMSS_summary.json
```

---

## Prompt de sistema (resumo)

Orientar o usuário na **melhor próxima ação** a partir de JSON e/ou imagem, sem inventar elementos ausentes; saída com análise do estado, ação recomendada e alternativas quando útil.

Prompt inicial de desenho gerado com ChatGPT; código aprimorado (Claude) para multimodalidade e logs.
