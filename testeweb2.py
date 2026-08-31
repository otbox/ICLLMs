from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, SessionNotCreatedException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pathlib import Path
import json
import re
import shutil
import subprocess
import time

# ==============================================================================
# ⚙️ CONFIGURAÇÃO
# ==============================================================================

# Paths relativos ao diretório deste script (não dependem do CWD)
BASE_DIR = Path(__file__).resolve().parent
URL = "https://www.americanas.com.br/brinquedos/dinossauros?category-1=brinquedos&category-2=dinossauros&fuzzy=0&operator=and&price=100-to-250&facets=category-1%2Ccategory-2%2Cfuzzy%2Coperator%2Cprice&sort=score_desc&page=0"
NOME_ARQUIVO_JSON = BASE_DIR / "extracoes/americanas/dinossauros/1c/estrutura_ui.json"
PASTA_SCREENS = BASE_DIR / "extracoes/americanas/dinossauros/1c/screenshots_ui"

HOVER_TRIGGER_CLASSES = [
    "MenuDesktop",
    "h-usr-link",
    "department-nav",
    "main-header",
]

WAIT_TIME_MENU_OPEN = 0.8
PAGE_LOAD_TIMEOUT = 20
MAIN_MENU_XPATH = "//a[@aria-haspopup='menu'] | //div[contains(@class, 'department-nav')]"
SUBMENU_XPATH = (
    "//section[contains(@class, 'Menu')] "
    "| //div[contains(@class, 'menuItemHovering')] "
    "| //ul[contains(@class, 'dropdown')]"
)


# ==============================================================================
# 🧠 FUNÇÕES AUXILIARES
# ==============================================================================

def ensure_output_dirs():
    """Cria pastas de saída (JSON + screenshots). Não precisa criar nada na mão."""
    PASTA_SCREENS.mkdir(parents=True, exist_ok=True)
    NOME_ARQUIVO_JSON.parent.mkdir(parents=True, exist_ok=True)


def reset_mouse(driver):
    """Fecha menus de hover movendo o mouse para um ponto seguro (não usa offset relativo)."""
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        ActionChains(driver).move_to_element_with_offset(body, 5, 5).perform()
    except Exception:
        try:
            driver.execute_script(
                "document.dispatchEvent(new MouseEvent('mousemove', "
                "{clientX: 0, clientY: 0, bubbles: true}));"
            )
        except Exception:
            pass


def get_clean_name(element):
    """Extrai um nome legível do elemento."""
    try:
        text = (element.text or "").split("\n")[0][:50].strip()
        return (
            text
            or element.get_attribute("title")
            or element.get_attribute("aria-label")
            or "Elemento sem nome"
        )
    except StaleElementReferenceException:
        return "Erro ao ler nome"
    except Exception:
        return "Erro ao ler nome"


def safe_filename(name, max_len=10):
    cleaned = re.sub(r"[^\w\-]+", "", (name or "")[:max_len], flags=re.UNICODE)
    return cleaned or "item"


def is_element_interactive(tag_name, class_name, element=None):
    if tag_name == "a" and element is not None:
        popup = element.get_attribute("aria-haspopup")
        if popup in ("menu", "true", "listbox"):
            return True

    if tag_name in ("button", "select", "textarea"):
        return True

    if class_name and any(k in class_name for k in HOVER_TRIGGER_CLASSES):
        return True

    return False


def append_child(target_list, child_data):
    """Normaliza retorno dict|list da recursão para sempre estender uma lista de dicts."""
    if not child_data:
        return
    if isinstance(child_data, list):
        target_list.extend(d for d in child_data if isinstance(d, dict))
    elif isinstance(child_data, dict):
        target_list.append(child_data)


# ==============================================================================
# 🕵️ LÓGICA DE EXTRAÇÃO
# ==============================================================================

def extract_element_data(element, level, driver):
    """
    Extrai dados do elemento. Em nós não-interativos retorna lista (flatten);
    em menus/interativos retorna dict. Sempre dict|list|None.
    """
    try:
        try:
            tag_name = element.tag_name.lower()
            current_classes = element.get_attribute("class") or ""
            element_name = get_clean_name(element)
        except StaleElementReferenceException:
            return None

        is_dropdown = False
        action_type = "click"

        if tag_name == "a" and element.get_attribute("aria-haspopup") == "menu":
            is_dropdown = True
            action_type = "hover"
        elif any(cls in current_classes for cls in HOVER_TRIGGER_CLASSES):
            is_dropdown = True
            action_type = "hover"

        data = {
            "nome": element_name,
            "classe": current_classes,
            "tipo": tag_name,
            "is_dropdown": is_dropdown,
            "acao": action_type,
            "nivel": level,
            "filhos": [],
        }

        if level > 0 and not element.is_displayed():
            return None

        # Container sem interação: desce filhos e achata
        if not is_dropdown and not is_element_interactive(tag_name, current_classes, element):
            try:
                for child in element.find_elements(By.XPATH, "./*"):
                    append_child(data["filhos"], extract_element_data(child, level, driver))
                return data["filhos"] if data["filhos"] else None
            except StaleElementReferenceException:
                return None
            except Exception:
                return None

        if is_dropdown and level < 3:
            sname = f"L{level}_{safe_filename(element_name)}_{int(time.time())}.png"
            try:
                element.screenshot(str(PASTA_SCREENS / sname))
                data["screenshot"] = sname
            except Exception:
                pass

        if is_dropdown:
            print(f"  {'  ' * level}↪️ [N{level}] Abrindo: '{element_name}'")
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                    element,
                )
                time.sleep(0.2)

                if action_type == "hover":
                    ActionChains(driver).move_to_element(element).perform()
                else:
                    if tag_name == "a":
                        driver.execute_script("arguments[0].removeAttribute('href');", element)
                    driver.execute_script("arguments[0].click();", element)

                time.sleep(WAIT_TIME_MENU_OPEN)

                submenu_container = None
                for menu in driver.find_elements(By.XPATH, SUBMENU_XPATH):
                    try:
                        size = menu.size
                        if (
                            menu.is_displayed()
                            and size.get("height", 0) > 20
                            and size.get("width", 0) > 20
                            and menu.id != element.id
                        ):
                            submenu_container = menu
                            break
                    except StaleElementReferenceException:
                        continue

                if submenu_container:
                    items_xpath = ".//a | .//button"
                    items_found = submenu_container.find_elements(By.XPATH, items_xpath)
                    print(f"    ✅ Container encontrado! {len(items_found)} itens detectados.")

                    seen = set()
                    for i in range(len(items_found)):
                        try:
                            # Re-busca a lista a cada item (evita stale)
                            items_found = submenu_container.find_elements(By.XPATH, items_xpath)
                            if i >= len(items_found):
                                break
                            current_item = items_found[i]
                            if not current_item.is_displayed():
                                continue

                            item_name = get_clean_name(current_item)
                            if not item_name or item_name in seen:
                                continue
                            seen.add(item_name)

                            item_link = (
                                current_item.get_attribute("href")
                                if current_item.tag_name.lower() == "a"
                                else ""
                            )
                            data["filhos"].append(
                                {
                                    "nome": item_name,
                                    "tipo": "ItemSubmenu",
                                    "link": item_link or "",
                                    "nivel": level + 1,
                                }
                            )
                        except StaleElementReferenceException:
                            continue
                else:
                    print(f"    ⚠️ Nenhum container de submenu visível para '{element_name}'.")

                reset_mouse(driver)
                time.sleep(0.3)

            except Exception as e:
                print(f"    ⚠️ Erro interação menu: {str(e)[:100]}")
                reset_mouse(driver)

    except Exception:
        return None

    return data


# ==============================================================================
# 🚀 DRIVER (Chromium local ↔ ChromeDriver compatível)
# ==============================================================================

CHROME_BINARIES = (
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
)


def find_chrome_binary():
    for path in CHROME_BINARIES:
        if Path(path).is_file():
            return path
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


def detect_browser_version(binary):
    """Retorna (versão_completa, major) a partir de `chromium --version`."""
    try:
        out = subprocess.check_output(
            [binary, "--version"], text=True, stderr=subprocess.STDOUT, timeout=10
        )
    except Exception:
        return None, None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", out)
    if not m:
        return None, None
    return m.group(0), m.group(1)


def build_chrome_options(binary):
    options = webdriver.ChromeOptions()
    if binary:
        options.binary_location = binary
    options.add_argument("--start-maximized")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return options


def create_driver():
    """
    Abre Chrome/Chromium com ChromeDriver na MESMA major version.
    Evita SessionNotCreatedException (ex.: driver 151 vs browser 148).
    """
    binary = find_chrome_binary()
    full_ver, major = detect_browser_version(binary) if binary else (None, None)
    options = build_chrome_options(binary)

    print(f"🌐 Browser: {binary or '(padrão)'} {full_ver or ''}".rstrip())

    # 1) Selenium Manager (Selenium 4.6+) — costuma casar sozinho com o binary
    try:
        driver = webdriver.Chrome(options=options)
        print("✅ Driver via Selenium Manager")
        return driver
    except SessionNotCreatedException as e:
        print(f"⚠️ Selenium Manager incompatível: {str(e).splitlines()[0]}")
    except Exception as e:
        print(f"⚠️ Selenium Manager falhou: {e}")

    # 2) webdriver-manager pinado na major do Chromium instalado
    if not major:
        raise RuntimeError(
            "Não foi possível detectar a versão do Chromium/Chrome. "
            "Instale chromium ou informe o binary."
        )

    print(f"⬇️ Baixando ChromeDriver major={major} (Chromium)...")
    driver_path = ChromeDriverManager(
        driver_version=major,
        chrome_type=ChromeType.CHROMIUM,
    ).install()
    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    print(f"✅ Driver via webdriver-manager: {driver_path}")
    return driver


# ==============================================================================
# 🚀 MAIN
# ==============================================================================

def main():
    ensure_output_dirs()
    print(f"📁 JSON → {NOME_ARQUIVO_JSON}")
    print(f"📁 Screenshots → {PASTA_SCREENS}")

    driver = create_driver()
    driver.set_page_load_timeout(60)

    try:
        print(f"🌐 Acessando {URL}...")
        driver.get(URL)

        try:
            WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, MAIN_MENU_XPATH))
            )
        except TimeoutException:
            print("⚠️ Timeout aguardando menus; tentando mesmo assim após espera curta...")
            time.sleep(3)

        print("🔍 Buscando menus principais...")
        main_menus = driver.find_elements(By.XPATH, MAIN_MENU_XPATH)
        count = len(main_menus)
        print(f"🎯 {count} menus principais identificados.")

        full_structure = []
        for i in range(count):
            try:
                current_menus = driver.find_elements(By.XPATH, MAIN_MENU_XPATH)
                if i >= len(current_menus):
                    break

                target_element = current_menus[i]
                if not target_element.is_displayed():
                    continue

                menu_data = extract_element_data(target_element, 0, driver)
                # Topo sempre lista de dicts (nunca lista aninhada solta)
                if isinstance(menu_data, dict):
                    full_structure.append(menu_data)
                elif isinstance(menu_data, list):
                    full_structure.extend(d for d in menu_data if isinstance(d, dict))

                reset_mouse(driver)
                time.sleep(0.5)

            except Exception as e:
                print(f"❌ Erro ao processar menu índice {i}: {e}")
                reset_mouse(driver)
                continue

        with open(NOME_ARQUIVO_JSON, "w", encoding="utf-8") as f:
            json.dump({"ui_structure": full_structure}, f, indent=4, ensure_ascii=False)

        print(f"✅ Concluído: {NOME_ARQUIVO_JSON} ({len(full_structure)} menus)")

    except Exception as e:
        print(f"❌ Erro fatal: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
