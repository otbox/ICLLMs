from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException, NoSuchElementException, ElementNotInteractableException
import json
import time
import os

# --- ⚙️ CONFIGURAÇÃO DE EXTRAÇÃO ⚙️ ---
URL = "https://www.americanas.com.br/" 
NOME_ARQUIVO_JSON = "extracoes/americanas/estrutura_ui.json"
PASTA_SCREENS = "extracoes/americanas/screenshots_ui"

# 🚨 Classes que identificam um elemento como DROPDOWN neste portal específico
CUSTOM_DROPDOWN_CLASSES = [
    "btnMenuDinamico",   # O botão de 'três pontinhos' ou menu suspenso dos widgets
    "lm_tabdropdown",    # Dropdown de abas do GoldenLayout (se houver muitas abas)
    "btn_filter"         # Botão de filtros interno
]

# 🚨 Classes que identificam elementos como INTERATIVOS (Botões/Links falsos feitos de DIVs/LIs)
# Baseado no HTML fornecido:
FORCED_INTERACTIVE_CLASSES = [
    "lm_tab",            # Abas (Exercício, Receita, Despesa)
    "temp05",            # Widgets de ícones (Acesso Rápido) - pega classes que começam com temp05
    "temp06",            # Widgets de lista (Dados resumidos) - pega classes que começam com temp06
    "btnMenu",           # Menu principal topo
    "circle_"            # Círculos de ano (embora geralmente estejam dentro de um <a>)
]

# Tempo de espera padrão após o clique no submenu
WAIT_TIME_AFTER_CLICK = 0.5
BREAKPOINT_PAUSE = 2.0

LEVEL_COUNTER = 0
# Tags padrão + tags estruturais que esse portal usa como botão
TAGS_INTERATIVAS_PADRAO = ['button', 'input', 'a', 'textarea', 'select']

def is_element_interactive(element, tag_name, class_name):
    """
    Verifica se um elemento é interativo baseando-se na Tag HTML OU nas Classes CSS específicas do portal.
    """
    # 1. Verificação por Tag Padrão
    if tag_name in TAGS_INTERATIVAS_PADRAO:
        return True
    
    # 2. Verificação por Classes Específicas (para DIVs e LIs que agem como botões)
    if class_name:
        for interactive_cls in FORCED_INTERACTIVE_CLASSES:
            if interactive_cls in class_name or class_name.startswith(interactive_cls):
                return True
            # Verificação especial para classes dinâmicas como 'temp05_1_...'
            if "temp05" in class_name or "temp06" in class_name:
                return True
                
    return False

def extract_element_data(element, level, driver):
    """
    Função recursiva que varre o GoldenLayout e extrai a estrutura.
    """
    global LEVEL_COUNTER
    LEVEL_COUNTER = level
    data = {}
    
    try:
        tag_name = element.tag_name.lower()
        
        # Tenta pegar atributos comuns
        element_id = element.get_attribute("id") or ""
        current_classes = element.get_attribute("class") or ""
        
        # --- Lógica de Nome (Tentativa de achar um texto útil) ---
        element_name = ""
        if tag_name == 'input':
            element_name = element.get_attribute("value") or element.get_attribute("placeholder") or ""
        else:
            # Tenta pegar texto direto. Se vazio, tenta 'title' (muito usado no seu HTML), ou 'aria-label'
            element_name = element.text[:100].strip()
            if not element_name:
                element_name = element.get_attribute("title") or ""
            
            # Ajuste para Widgets 'temp05' e 'temp06': O nome geralmente está numa div filha com classe 'titulo05' ou 'titulo01'
            if not element_name and ("temp05" in current_classes or "temp06" in current_classes):
                try:
                    title_elem = element.find_element(By.CSS_SELECTOR, "[class*='titulo']")
                    element_name = title_elem.text.strip()
                except:
                    pass

        # --- 1. Lógica de Bypass (Se não for interativo, ignora e pega os filhos) ---
        if not is_element_interactive(element, tag_name, current_classes):
            data["filhos"] = []
            
            # Estratégia de busca de filhos:
            # No GoldenLayout, às vezes é melhor buscar filhos específicos para não pegar lixo
            try:
                children = element.find_elements(By.XPATH, "./*")
                for child in children:
                    child_data = extract_element_data(child, level, driver) # Repassa driver
                    if child_data:
                        if isinstance(child_data, list):
                            data["filhos"].extend(child_data)
                        elif isinstance(child_data, dict):
                            data["filhos"].append(child_data)
            except StaleElementReferenceException:
                pass # Elemento mudou durante a leitura
            except Exception:
                pass

            return data["filhos"] if data["filhos"] else None

        # --- 2. Processamento de Elemento Interativo Detectado ---
        
        # Detecta se é Dropdown
        is_dropdown_flag = (tag_name == 'select')
        if not is_dropdown_flag and current_classes:
            if any(cls in current_classes for cls in CUSTOM_DROPDOWN_CLASSES):
                is_dropdown_flag = True

        data["is_dropdown"] = is_dropdown_flag
        data["nome"] = element_name
        data["classe"] = current_classes
        data["tag"] = tag_name
        data["tipo_controle"] = "CustomWidget" if "temp" in current_classes else tag_name.capitalize()
        data["nivel"] = level
        
        # Posição e Visibilidade
        try:
            data["posicao"] = { "x": element.location['x'], "y": element.location['y'], "w": element.size['width'], "h": element.size['height'] }
            data["visivel"] = element.is_displayed()
            data["habilitado"] = element.is_enabled()
        except:
             data["visivel"] = False # Se falhar ao pegar posição, assume oculto/stale

        data["id_automacao"] = element_id
        data["ignorado"] = not data["visivel"]
        
        # Screenshot
        if data["visivel"]:
            screenshot_filename = f"L{level}_{tag_name}_{int(time.time()*1000)}.png"
            screenshot_path = os.path.join(PASTA_SCREENS, screenshot_filename)
            if not os.path.exists(PASTA_SCREENS): os.makedirs(PASTA_SCREENS)
            try:
                element.screenshot(screenshot_path)
                data["screenshot"] = screenshot_filename
            except:
                data["screenshot"] = ""
        
        # --- 3. Processamento de Submenus/Dropdows ---
        data["filhos"] = []
        
        if data["is_dropdown"] and data["visivel"]:
            print(f"  ↪️ Menu/Dropdown detectado: '{data['nome']}' ({data['classe']})")
            
            try:
                # Rola até o elemento e clica via JS para evitar erros de sobreposição
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", element)
                time.sleep(WAIT_TIME_AFTER_CLICK) 

                # Localização do container do submenu
                submenu_container = None
                
                # Regra específica para o seu HTML: 
                # O menu 'menuDinamico' está DENTRO da div 'btnMenuDinamico' (que é o botão), 
                # mas inicialmente escondido (display: none). Ao clicar, ele vira display: block.
                try:
                    # Busca dentro do próprio elemento primeiro (estrutura comum nesse HTML)
                    submenu_container = element.find_element(By.CSS_SELECTOR, ".menuDinamico")
                    if not submenu_container.is_displayed():
                        # Se não achou dentro, tenta procurar um parente próximo ou irmão
                        submenu_container = element.find_element(By.XPATH, "./following-sibling::*[contains(@class, 'menuDinamico')]")
                except:
                    pass

                # Extração dos itens do submenu
                if submenu_container and submenu_container.is_displayed():
                    # No seu HTML, os itens do menu são LIs dentro de ULs
                    submenu_items = submenu_container.find_elements(By.CSS_SELECTOR, "li")
                    
                    for sub_item in submenu_items:
                        child_data = extract_element_data(sub_item, level + 1, driver)
                        if child_data and isinstance(child_data, dict):
                            data["filhos"].append(child_data)
                    
                    print(f"    ✅ Itens extraídos: {len(data['filhos'])}")
                
                # Fecha o menu clicando novamente via JS
                driver.execute_script("arguments[0].click();", element)
                time.sleep(0.3)
                
            except Exception as e:
                print(f"    ⚠️ Erro ao interagir com menu: {e}")

        # Se não for dropdown, ainda pode ter filhos (ex: um Widget temp05 pode ter ícone e texto dentro)
        # Mas para evitar duplicação excessiva, só buscamos filhos de interativos se não for dropdown
        elif not data["is_dropdown"]:
             # Opcional: Se quiser pegar detalhes internos do botão, descomente abaixo. 
             # Para o seu caso, geralmente não precisa pois já pegamos o 'nome' e 'classe'.
             pass

    except StaleElementReferenceException:
        return None
    except Exception as e:
        # print(f"Erro genérico elemento: {e}")
        return None
        
    return data

def salvar_json_em_arquivo(data, nome_arquivo):
    try:
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"\n✅ JSON salvo em: {os.path.abspath(nome_arquivo)}")
    except IOError as e:
        print(f"\n❌ Erro ao salvar JSON: {e}")

def scrape_ui_structure(url):
    if not os.path.exists(PASTA_SCREENS):
        os.makedirs(PASTA_SCREENS)

    options = webdriver.ChromeOptions()
    # options.add_argument("--headless") # Descomente para rodar sem janela
    options.add_argument("--start-maximized")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.get(url)
        print("⏳ Aguardando carregamento total do Dashboard (10s)...")
        time.sleep(10) # GoldenLayout demora para montar o DOM

        # Pega o body ou o container principal do GoldenLayout
        try:
            root_element = driver.find_element(By.ID, "MainDiv") # Focando no container principal do seu HTML
        except:
            root_element = driver.find_element(By.TAG_NAME, "body")
        
        ui_structure_data = extract_element_data(root_element, 0, driver) 
        
        final_json = { "ui_structure": ui_structure_data }
        return final_json
        
    except Exception as e:
        print(f"❌ Erro fatal na extração: {e}")
        return None
    finally:
        driver.quit()

# --- Execução ---
if __name__ == "__main__":
    print(f"Iniciando varredura no portal: {URL}")
    ui_json = scrape_ui_structure(URL)

    if ui_json:
        salvar_json_em_arquivo(ui_json, NOME_ARQUIVO_JSON)
        print("✨ Processo finalizado.")