
# ICLLMs - Windows UI Extractor

Este projeto é uma ferramenta de automação desenvolvida para extrair a árvore de componentes de interface de usuário (UI) de aplicações Windows.

O extrator navega recursivamente pela aplicação alvo (como o LibreOffice, Bloco de Notas, etc.), captura propriedades detalhadas de cada elemento, tira screenshots individuais e gera um arquivo JSON estruturado contendo toda a hierarquia da interface.

## 🚀 Funcionalidades

-   **Extração Recursiva**: Mapeia janelas, botões, menus, listas e barras de ferramentas.
    
-   **Captura Visual**: Salva screenshots (recortes) de cada elemento UI detectado.
    
-   **Multi-threading Opcional**: Acelera a extração usando múltiplas threads para processar filhos de contêineres grandes.
    
-   **Sistema de Banlist**: Permite ignorar elementos irrelevantes (como sombras de sistema, tooltips ou menus específicos) para limpar o dataset.
    
-   **Expansão de Menus**: Tenta interagir e expandir menus para capturar sub-itens ocultos.
    

## 📋 Pré-requisitos

-   **Sistema Operacional**: Windows 10 ou 11 (Necessário devido ao uso da API de Automação do Windows/pywinauto).
    
-   **Python**: 3.8 ou superior.
    

## 📦 Instalação

1.  Clone este repositório ou baixe os arquivos.
    
2.  Instale as dependências listadas no `requirements.txt`:
    

```
pip install -r requirements.txt

```

## ⚙️ Configuração

Antes de executar, abra o arquivo `ui_extractor_advanced.py` e vá até a seção **ENTRY POINT** (final do arquivo) para ajustar as configurações:

### 1. Definir o Alvo (`ExtractorConfig`)

Aponte para o executável que deseja mapear:

```
configuracao = ExtractorConfig(
    app_path=r"C:\Program Files\LibreOffice\program\swriter.exe", # Caminho do executável
    output_file="resultado_ui.json",
    use_multithreading=True,  # True para velocidade, False para estabilidade
    max_workers=4,            # Número de threads
    take_screenshots=True     # Se deve salvar imagens dos elementos
)

```

### 2. Configurar a Banlist (`BanlistConfig`)

Evite ruído no seu dataset bloqueando elementos desnecessários:

```
minha_banlist = BanlistConfig(
    nomes_exatos={"Barra de título", "System", "Fechar"}, # Ignora pelo nome exato
    classes={"SysShadow", "ToolTip"},                     # Ignora pela classe da janela
    nomes_parciais={}                                     # Ignora se conter o texto
)

```

## ▶️ Como Usar

Com as configurações ajustadas, execute o script:

```
python ui_extractor_advanced.py

```

O script irá:

1.  Iniciar a aplicação alvo.
    
2.  Aguardar o carregamento da janela.
    
3.  Varrer toda a árvore de elementos.
    
4.  Salvar as imagens na pasta `screenshots/`.
    
5.  Gerar o arquivo JSON final.
    

## 📄 Formato de Saída (JSON)

O arquivo gerado segue a estrutura hierárquica abaixo:

```
{
  "ui_structure": {
    "nome": "Sem título 1 — LibreOffice Writer",
    "classe": "SALFRAME",
    "tipo_controle": "Window",
    "nivel": 0,
    "posicao": {
      "x": 85,
      "y": 83,
      "w": 1440,
      "h": 753
    },
    "visivel": true,
    "habilitado": true,
    "id_automacao": "",
    "ignorado": false,
    "screenshot": "L0_Sem_título_1_—_LibreOffice_Writer_1764098159396.png",
    "filhos": [
      {
        "nome": "",
        "classe": "",
        "tipo_controle": "TitleBar",
        "nivel": 1,
        "posicao": {
          "x": 109,
          "y": 86,
          "w": 1408,
          "h": 28
        },
        "filhos": []
      }
    ]
  }
}

```

## ⚠️ Notas Importantes

-   **Interferência**: Evite usar o mouse e teclado enquanto o script roda, pois ele simula cliques para abrir menus.
    
-   **Permissões**: Algumas aplicações podem exigir que o script rode como Administrador.
    
-   **Multithreading**: O modo multi-thread é muito mais rápido, mas pode causar instabilidade em algumas aplicações legadas. Se houver falhas, mude `use_multithreading=False`.