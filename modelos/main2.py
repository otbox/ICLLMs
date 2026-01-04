"""
Sistema de Comparação Multi-Modelo com OpenRouter
Executa a mesma pergunta em vários modelos e salva resultados em arquivos
"""

import os
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configura cliente OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    default_headers={"HTTP-Referer": "http://localhost:5000"}
)

# ROLE do sistema (sua regra customizada)
SYSTEM_ROLE = """Você é um sistema especializado em análise de estruturas e orientação de tarefas.
Seu objetivo é guiar o usuário para tomar a melhor próxima ação possível.

ENTRADA
Você receberá exatamente um dos itens abaixo:
- JSON contendo dados, etapas, opções ou componentes.
- Imagem representando tela, componentes, interface, objetos ou ambiente.

OBJETIVO
A partir dessa entrada, você deve:
1. Interpretar com precisão todos os elementos relevantes.
2. Identificar o estado atual da tarefa do usuário.
3. Determinar a melhor próxima ação disponível.
4. Dar instruções claras, diretas, executáveis.

Se houver múltiplas ações possíveis, escolha a mais eficiente e explique brevemente o motivo.

REGRAS
- Nunca invente informações que não estejam no JSON ou imagem.
- Nunca peça dados adicionais, a menos que sejam estritamente necessários.
- Se a entrada for um JSON, use apenas os campos fornecidos.
- Se a entrada for uma imagem, descreva apenas o que é visível.

A saída deve sempre conter:
- Análise objetiva do estado atual.
- Melhor ação recomendada.
- Caso útil, alternativas e seus custos/benefícios."""

# Lista de modelos para comparação
MODELS = [
    # OpenAI
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    
    # Anthropic Claude
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-haiku",
    
    # Google Gemini
    "google/gemini-2.0-flash-exp:free",
    "google/gemini-pro-1.5",
    
    # Meta Llama (gratuitos)
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct:free",
    
    # Mistral
    "mistralai/mistral-7b-instruct:free",
    
    # DeepSeek
    "deepseek/deepseek-chat",
]

def query_model_with_messages(model_name, messages, temperature=0.7, max_tokens=1000):
    """
    Consulta um modelo específico com mensagens customizadas
    
    Args:
        model_name: Nome do modelo no OpenRouter
        messages: Lista de mensagens (sistema, usuário, assistente)
        temperature: Temperatura (0-2)
        max_tokens: Máximo de tokens na resposta
    
    Returns:
        Dict com resultado ou erro
    """
    try:
        start_time = datetime.now()
        
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return {
            "model": model_name,
            "status": "success",
            "response": response.choices[0].message.content,
            "duration_seconds": duration,
            "tokens_used": {
                "prompt": response.usage.prompt_tokens if hasattr(response, 'usage') else None,
                "completion": response.usage.completion_tokens if hasattr(response, 'usage') else None,
                "total": response.usage.total_tokens if hasattr(response, 'usage') else None
            },
            "timestamp": start_time.isoformat()
        }
        
    except Exception as e:
        return {
            "model": model_name,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

def compare_models_with_context(user_prompt, context_json=None, models=None, output_dir="model_responses", parallel=True):
    """
    Compara modelos mantendo JSON como contexto
    
    Args:
        user_prompt: Sua pergunta
        context_json: JSON (string ou dict) que será mantido como contexto
        models: Lista de modelos (usa MODELS padrão se None)
        output_dir: Diretório de saída
        parallel: Se True, executa em paralelo
    
    Returns:
        Lista com resultados de todos os modelos
    """
    if models is None:
        models = MODELS
    
    # Prepara mensagens com contexto persistente
    messages = [{"role": "system", "content": SYSTEM_ROLE}]
    
    # Adiciona JSON como contexto inicial (apenas uma vez)
    if context_json:
        if isinstance(context_json, dict):
            context_json = json.dumps(context_json, indent=2, ensure_ascii=False)
        messages.append({
            "role": "user", 
            "content": f"Contexto inicial (JSON):\n{context_json}"
        })
        messages.append({
            "role": "assistant",
            "content": "JSON recebido e analisado. Pronto para responder perguntas sobre ele."
        })
    
    # Adiciona a pergunta atual
    messages.append({"role": "user", "content": user_prompt})
    
    # Cria diretório de saída
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Timestamp para esta execução
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"Executando {len(models)} modelos...")
    if context_json:
        print(f"Com contexto JSON ({len(context_json)} caracteres)")
    print(f"Pergunta: {user_prompt[:100]}...\n")
    
    results = []
    
    if parallel:
        # Execução paralela (mais rápido)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(query_model_with_messages, model, messages): model 
                for model in models
            }
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                
                # Feedback em tempo real
                if result["status"] == "success":
                    print(f"✓ {result['model']} - {result['duration_seconds']:.2f}s")
                else:
                    print(f"✗ {result['model']} - ERRO: {result['error']}")
    else:
        # Execução sequencial
        for model in models:
            result = query_model_with_messages(model, messages)
            results.append(result)
            
            if result["status"] == "success":
                print(f"✓ {result['model']} - {result['duration_seconds']:.2f}s")
            else:
                print(f"✗ {result['model']} - ERRO: {result['error']}")
    
    # Salva resultados individuais
    for result in results:
        # Nome do arquivo sanitizado
        model_safe_name = result["model"].replace("/", "_").replace(":", "_")
        filename = f"{timestamp}_{model_safe_name}.txt"
        filepath = output_path / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"MODELO: {result['model']}\n")
            f.write(f"STATUS: {result['status']}\n")
            f.write(f"TIMESTAMP: {result['timestamp']}\n")
            
            if result['status'] == 'success':
                f.write(f"DURAÇÃO: {result['duration_seconds']:.2f}s\n")
                if result['tokens_used']['total']:
                    f.write(f"TOKENS: {result['tokens_used']['total']}\n")
                f.write("\n" + "="*80 + "\n")
                f.write("CONTEXTO JSON:\n")
                if context_json:
                    f.write(context_json if isinstance(context_json, str) else json.dumps(context_json, indent=2))
                else:
                    f.write("(nenhum)")
                f.write("\n\n" + "="*80 + "\n")
                f.write("PERGUNTA:\n")
                f.write(user_prompt + "\n\n")
                f.write("="*80 + "\n")
                f.write("RESPOSTA:\n")
                f.write(result['response'])
            else:
                f.write(f"ERRO: {result['error']}\n")
    
    # Salva resumo consolidado JSON
    summary_file = output_path / f"{timestamp}_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "prompt": user_prompt,
            "context_json": context_json if isinstance(context_json, str) else json.dumps(context_json) if context_json else None,
            "timestamp": timestamp,
            "total_models": len(models),
            "successful": len([r for r in results if r['status'] == 'success']),
            "failed": len([r for r in results if r['status'] == 'error']),
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Resultados salvos em: {output_path.absolute()}")
    print(f"  - {len(results)} arquivos individuais")
    print(f"  - 1 arquivo resumo: {summary_file.name}")
    
    return results

def interactive_comparison_with_context():
    """Modo interativo com suporte a contexto JSON"""
    print("=== Comparação Multi-Modelo com Contexto ===\n")
    
    # Pergunta se há contexto JSON
    use_context = input("Deseja usar um JSON como contexto? (s/n): ").strip().lower()
    
    context_json = None
    if use_context == 's':
        print("\nOpções:")
        print("1. Colar JSON diretamente")
        print("2. Carregar de arquivo")
        option = input("Escolha (1/2): ").strip()
        
        if option == "1":
            print("\nCole o JSON (termine com linha vazia):")
            lines = []
            while True:
                line = input()
                if not line:
                    break
                lines.append(line)
            context_json = "\n".join(lines)
        elif option == "2":
            filepath = input("Caminho do arquivo JSON: ").strip()
            with open(filepath, 'r', encoding='utf-8') as f:
                context_json = f.read()
    
    # Seleção de modelos
    print("\nModelos disponíveis:")
    for i, model in enumerate(MODELS, 1):
        print(f"  {i}. {model}")
    
    print("\nDigite 'all' para usar todos ou números separados por vírgula (ex: 1,3,5)")
    selection = input("Selecione modelos: ").strip()
    
    if selection.lower() == 'all':
        selected_models = MODELS
    else:
        indices = [int(x.strip()) - 1 for x in selection.split(',')]
        selected_models = [MODELS[i] for i in indices if 0 <= i < len(MODELS)]
    
    print(f"\n{len(selected_models)} modelo(s) selecionado(s)")
    
    # Pergunta do usuário
    prompt = input("\nDigite sua pergunta: ").strip()
    
    if not prompt:
        print("Pergunta vazia. Abortando.")
        return
    
    # Executa comparação com contexto
    compare_models_with_context(prompt, context_json=context_json, models=selected_models)

# Exemplo de uso com contexto
def exemplo_com_contexto():
    """Exemplo automático usando contexto JSON"""
    
    # Define JSON de contexto
    with open('/home/tboxo/Documentos/Projetos/ICLLMs/extracoes/americanas/estrutura_ui.json', 'r') as d:
        json_projeto = json.load(d) 
        
    
    # Pergunta sobre o contexto
    pergunta = "Minha tarefa é procurar um brinquedo de dinossorauro na faixa de 100 a 250 reais"
    
    # Modelos para teste
    modelos_teste = [
        "tngtech/deepseek-r1t2-chimera:free",
        "kwaipilot/kat-coder-pro:free",
        "mistralai/devstral-2512:free",
        "nvidia/nemotron-nano-12b-v2-vl:free"
    ]
    
    # Executa comparação
    compare_models_with_context(
        user_prompt=pergunta,
        context_json=json_projeto,
        models=modelos_teste
    )

if __name__ == "__main__":
    # Descomente a opção desejada:
    
    # Modo interativo com contexto
    # interactive_comparison_with_context()
    
    # Exemplo automático
    exemplo_com_contexto()
