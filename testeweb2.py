from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException, NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.action_chains import ActionChains
import json
import time
import os

# ==============================================================================
# ⚙️ CONFIGURAÇÃO
# ==============================================================================

URL = "https://www.americanas.com.br/" 
NOME_ARQUIVO_JSON = "extracoes/americanas/nossaslojas2/estrutura_ui.json"
PASTA_SCREENS = "extracoes/americanas/nossaslojas2/screenshots_ui"

# Classes que indicam que o elemento é um MENU (Trigger)
HOVER_TRIGGER_CLASSES = [
    "MenuDesktop", 
    "h-usr-link", 
    "department-nav",
    "main-header"
]

# Configurações de Tempo
WAIT_TIME_MENU_OPEN = 0.8
LEVEL_COUNTER = 0

# ==============================================================================
# 🧠 FUNÇÕES AUXILIARES
# ==============================================================================

def reset_mouse(driver):
    """Move o mouse para o canto (0,0) para fechar menus de hover."""
    try:
        ActionChains(driver).move_by_offset(-1000, -1000).perform() # Tenta mover para fora
        ActionChains(driver).move_to_element(driver.find_element(By.TAG_NAME, "body")).perform() # Move para o body seguro
    except: pass

def get_clean_name(element):
    """Tenta extrair um nome legível do elemento."""
    try:
        return element.text.split("\n")[0][:50].strip() or element.get_attribute("title") or element.get_attribute("aria-label") or "Elemento sem nome"
    except: return "Erro ao ler nome"

def is_element_interactive(tag_name, class_name, element=None):
    # Regra 1: Links com aria-haspopup (Menu Americanas)
    if tag_name == 'a' and element:
        popup = element.get_attribute("aria-haspopup")
        if popup in ["menu", "true", "listbox"]:
            return True
        
    # Regra 2: Tags padrão
    if tag_name in ['button', 'select', 'textarea']:
        return True
    
    # Regra 3: Classes de menu conhecidas
    if class_name and any(k in class_name for k in HOVER_TRIGGER_CLASSES):
        return True
            
    return False

# ==============================================================================
# 🕵️ LÓGICA DE EXTRAÇÃO ROBUSTA
# ==============================================================================

def extract_element_data(element, level, driver, parent_xpath=""):
    """
    Função recursiva com LOOP POR ÍNDICE para evitar StaleElementReferenceException.
    """
    global LEVEL_COUNTER
    LEVEL_COUNTER = level
    data = {}
    
    try:
        # --- 1. DADOS BÁSICOS ---
        try:
            tag_name = element.tag_name.lower()
            current_classes = element.get_attribute("class") or ""
            element_name = get_clean_name(element)
        except StaleElementReferenceException:
            return None # Elemento morreu, ignora.

        # --- 2. CLASSIFICAÇÃO DA AÇÃO ---
        is_dropdown = False
        action_type = "click"

        # Detecta Hover (Americanas usa links com aria-haspopup="menu")
        if tag_name == 'a' and element.get_attribute("aria-haspopup") == "menu":
            is_dropdown = True
            action_type = "hover"
        
        # Outros tipos de menu
        elif any(cls in current_classes for cls in HOVER_TRIGGER_CLASSES):
            is_dropdown = True
            action_type = "hover"

        # --- 3. PREENCHE DADOS JSON ---
        data = {
            "nome": element_name,
            "classe": current_classes,
            "tipo": f"{tag_name}",
            "is_dropdown": is_dropdown,
            "acao": action_type,
            "nivel": level,
            "filhos": []
        }

        # Ignora elementos invisíveis (exceto se for um container raiz)
        if level > 0 and not element.is_displayed():
            return None
        
        # Se NÃO for dropdown/interativo, buscamos os filhos diretos e retornamos
        if not is_dropdown and not is_element_interactive(tag_name, current_classes, element):
            try:
                children = element.find_elements(By.XPATH, "./*")
                for child in children:
                    child_data = extract_element_data(child, level, driver) # Mantém nível visualmente
                    if child_data:
                        if isinstance(child_data, list): data["filhos"].extend(child_data) # Flatten
                        elif isinstance(child_data, dict): data["filhos"].append(child_data)
                return data["filhos"] if data["filhos"] else None
            except: return None

        # Screenshot (Economia de espaço)
        if is_dropdown and level < 3:
            sname = f"L{level}_{element_name[:10].replace('/','').replace(' ','')}_{int(time.time())}.png"
            try: element.screenshot(os.path.join(PASTA_SCREENS, sname)); data["screenshot"] = sname
            except: pass

        # --- 4. INTERAÇÃO E BUSCA DO SUBMENU (CORREÇÃO DE LOOP) ---
        
        if is_dropdown:
            print(f"  {'  ' * level}↪️ [N{level}] Abrindo: '{element_name}'")
            
            try:
                # 1. Realiza Ação (Hover ou Click)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", element)
                time.sleep(0.2)
                
                if action_type == "hover":
                    ActionChains(driver).move_to_element(element).perform()
                else:
                    if tag_name == 'a': # Vacina anti-navegação
                        driver.execute_script("arguments[0].removeAttribute('href');", element)
                    driver.execute_script("arguments[0].click();", element)
                
                time.sleep(WAIT_TIME_MENU_OPEN)

                # 2. BUSCA DO CONTAINER DO SUBMENU
                # Procura por SECTIONS/DIVS que se tornaram visíveis. 
                # O segredo é buscar elementos com "Menu" ou "content" que estão visíveis AGORA.
                submenu_container = None
                
                # Seletores genéricos para encontrar o painel que abriu
                possible_menus = driver.find_elements(By.XPATH, 
                    "//section[contains(@class, 'Menu')] | //div[contains(@class, 'menuItemHovering')] | //ul[contains(@class, 'dropdown')]")
                
                for menu in possible_menus:
                    if menu.is_displayed() and menu.size['height'] > 20 and menu.size['width'] > 20:
                        # Ignora o próprio elemento pai se ele foi capturado
                        if menu.id != element.id:
                            submenu_container = menu
                            break 

                # 3. EXTRAÇÃO DOS ITENS DO SUBMENU (COM LOOP ROBUSTO)
                if submenu_container:
                    # Encontra TODOS os links/botões dentro do menu aberto
                    # Usamos um seletor genérico para pegar tudo que é clicável lá dentro
                    items_xpath = ".//a | .//button | .//li"
                    items_found = submenu_container.find_elements(By.XPATH, items_xpath)
                    count_items = len(items_found)
                    
                    print(f"    ✅ Container encontrado! {count_items} itens detectados.")

                    # 🚨 AQUI ESTÁ O FIX: Loop por índice e reaquisição
                    # Como não vamos clicar nos filhos (somente leitura), podemos iterar a lista 'items_found' diretamente
                    # SE precisássemos clicar neles, teríamos que usar o range(count).
                    
                    for i in range(count_items):
                        try:
                            # Reencontra o container e o item a cada iteração para garantir que não está Stale
                            # Nota: Se o submenu for apenas para leitura (links finais), não precisamos re-hoverar o pai.
                            # Mas se o submenu tiver sub-submenus, a lógica ficaria bem mais complexa.
                            # Para Americanas, assumimos que o nível 2 são links finais ou categorias simples.
                            
                            current_item = items_found[i]
                            
                            # Verifica se ainda está visível e anexado ao DOM
                            if current_item.is_displayed():
                                item_name = get_clean_name(current_item)
                                item_link = current_item.get_attribute("href") if current_item.tag_name == 'a' else ""
                                
                                if item_name:
                                    data["filhos"].append({
                                        "nome": item_name,
                                        "tipo": "ItemSubmenu",
                                        "link": item_link,
                                        "nivel": level + 1
                                    })
                        except StaleElementReferenceException:
                            # Se deu stale, tenta recuperar o container e a lista (recuperação de falha)
                            continue

                else:
                    print(f"    ⚠️ Nenhum container de submenu visível detectado para '{element_name}'.")

                # 4. FECHAR MENU (CRÍTICO PARA IR PRO PRÓXIMO)
                reset_mouse(driver)
                time.sleep(0.3)

            except Exception as e:
                print(f"    ⚠️ Erro interação menu: {str(e)[:100]}")
                reset_mouse(driver)

    except Exception: return None
    return data

# ==============================================================================
# 🚀 MAIN
# ==============================================================================

def main():
    if not os.path.exists(PASTA_SCREENS): os.makedirs(PASTA_SCREENS)
    
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--ignore-certificate-errors")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        print(f"🌐 Acessando {URL}...")
        driver.get(URL)
        time.sleep(8) 

        # 🚨 ESTRATÉGIA DE NÍVEL SUPERIOR:
        # Em vez de chamar a recursão no BODY, vamos identificar os MENUS PRINCIPAIS
        # e iterar sobre eles manualmente com o Loop Robusto. Isso evita que o robô se perca.
        
        print("🔍 Buscando menus principais...")
        
        # 1. Encontra todos os links que parecem menus principais (Header)
        # Ajuste esse XPath para pegar a barra horizontal principal ou o botão "Todos os departamentos"
        main_menus = driver.find_elements(By.XPATH, "//a[@aria-haspopup='menu'] | //div[contains(@class, 'department-nav')]")
        
        full_structure = []
        count = len(main_menus)
        print(f"🎯 {count} menus principais identificados para análise profunda.")

        # 2. Loop Robusto de Nível Superior
        for i in range(count):
            try:
                # Re-adquire a lista de menus principais (O DOM pode ter mudado)
                current_menus = driver.find_elements(By.XPATH, "//a[@aria-haspopup='menu'] | //div[contains(@class, 'department-nav')]")
                if i >= len(current_menus): break # Segurança
                
                target_element = current_menus[i]
                
                # Chama a extração apenas para este menu
                if target_element.is_displayed():
                    menu_data = extract_element_data(target_element, 0, driver)
                    if menu_data:
                        full_structure.append(menu_data)
                    
                # Garante que tudo esteja fechado antes de ir pro próximo menu principal
                reset_mouse(driver)
                time.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Erro ao processar menu índice {i}: {e}")
                continue

        # Salva
        with open(NOME_ARQUIVO_JSON, 'w', encoding='utf-8') as f:
            json.dump({"ui_structure": full_structure}, f, indent=4, ensure_ascii=False)
        print(f"✅ Concluído: {NOME_ARQUIVO_JSON}")

    except Exception as e:
        print(f"❌ Erro fatal: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()