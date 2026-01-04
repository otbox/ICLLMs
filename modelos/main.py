import requests
import json
import threading

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Carrega variáveis de ambiente
load_dotenv()

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY não encontrada. Configure no arquivo .env")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
    default_headers={"HTTP-Referer": "http://localhost:5000"}
)

SYSTEM_ROLE = """Você é um sistema especializado em análise de estruturas e orientação de tarefas.
Seu objetivo é guiar o usuário para tomar a melhor próxima ação possível.

ENTRADA
Você receberá exatamente um dos itens abaixo:
- JSON contendo dados, etapas, opções, componentes ou estado da tarefa.
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

conversation_history = []

def analyze_structure(user_input, model="openai/gpt-4o-mini"):
    conversation_history.append({
        "role": "user",
        "content": user_input
    })
    
    # Monta as mensagens incluindo o ROLE do sistema
    messages = [{"role": "system", "content": SYSTEM_ROLE}] + conversation_history
    
    # Faz chamada à API
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        # max_tokens=1000
    )
    
    # Extrai resposta
    assistant_message = response.choices[0].message.content
    file_path = f"output_{model}.txt"
    with open(file_path, "a") as file:
        file.write(str(assistant_message) + "\n")  

    
    
    # Adiciona resposta ao histórico
    conversation_history.append({
        "role": "assistant",
        "content": assistant_message
    })
    
    return assistant_message

def analyze_json_file(filepath):
    MODELS = ["", "", ""]
    
    print("=== Sistema de Análise de Estruturas ===")
    print("\nComandos disponíveis:")
    print("  - Digite sua pergunta ou cole um JSON")
    print("  - 'file:<caminho>' para analisar arquivo JSON")
    print("  - 'history' para ver histórico")
    print("  - 'clear' para limpar histórico")
    print("  - 'exit' para sair\n")
    
    while True:
        try:
            user_input = input("\n>>> Você: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() == 'exit':
                print("Encerrando...")
                break
                
            if user_input.lower() == 'clear':
                conversation_history.clear()
                print("Histórico limpo.")
                continue
                
            if user_input.lower() == 'history':
                print("\n--- Histórico ---")
                for msg in conversation_history:
                    role = "Você" if msg["role"] == "user" else "Assistente"
                    print(f"\n{role}: {msg['content'][:100]}...")
                continue
                
            if user_input.lower().startswith('file:'):
                filepath = user_input[5:].strip()
                response = analyze_json_file(filepath)
            else:
                for model in MODELS:
                    threading
                    response = analyze_structure(user_input, model)
            
            print(f"\n>>> Assistente: {response}")
            
        except KeyboardInterrupt:
            print("\n\nEncerrando...")
            break
        except Exception as e:
            print(f"\nErro: {e}")