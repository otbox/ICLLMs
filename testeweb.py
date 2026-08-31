from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from selenium.common.exceptions import (
    StaleElementReferenceException,
    SessionNotCreatedException,
    TimeoutException,
)
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import time

# ==============================================================================
# ⚙️ CONFIGURAÇÃO PADRÃO
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_URL = (
    "https://www.americanas.com.br/brinquedos?chave=pfm_home_brinquedos_menu"
)
DEFAULT_JSON = BASE_DIR / "extracoes/americanas/brinquedos/1b/estrutura_ui.json"
DEFAULT_SCREENS = BASE_DIR / "extracoes/americanas/brinquedos/1b/screenshots_ui"

# Limeira / portais com dropdowns customizados
CUSTOM_DROPDOWN_CLASSES = [
    "btnMenuDinamico",
    "lm_tabdropdown",
    "btn_filter",
]

# DIVs/LIs que agem como botão (Limeira)
FORCED_INTERACTIVE_CLASSES = [
    "lm_tab",
    "temp05",
    "temp06",
    "btnMenu",
    "circle_",
]

# Triggers de menu hover (Americanas e similares)
HOVER_TRIGGER_CLASSES = [
    "MenuDesktop",
    "h-usr-link",
    "department-nav",
    "main-header",
]

TAGS_INTERATIVAS_PADRAO = ["button", "input", "a", "textarea", "select"]

WAIT_TIME_AFTER_CLICK = 0.15
WAIT_TIME_MENU_OPEN = 0.25
TIME_TO_START = 4
PAGE_LOAD_TIMEOUT = 15
SCREENSHOT_MIN_SIZE = 8  # px; ignora recortes minúsculos
PROGRESS_EVERY = 25

# Snapshot em 1 round-trip (bem mais rápido que location/text/is_displayed separados)
JS_ELEMENT_SNAPSHOT = """
const el = arguments[0];
if (!el || !el.getBoundingClientRect) return null;
const r = el.getBoundingClientRect();
const st = window.getComputedStyle(el);
let name = '';
const tag = (el.tagName || '').toLowerCase();
if (tag === 'input' || tag === 'textarea') {
  name = (el.value || el.placeholder || '').trim();
} else {
  const t = (el.innerText || '').trim();
  name = t ? t.split('\\n')[0].trim().slice(0, 100) : '';
}
if (!name) name = (el.title || el.getAttribute('aria-label') || '').trim().slice(0, 100);
const visible = st.display !== 'none' && st.visibility !== 'hidden'
  && Number(st.opacity) !== 0 && r.width > 0 && r.height > 0;
return {
  tag: tag,
  id: el.id || '',
  className: (typeof el.className === 'string' ? el.className : (el.getAttribute('class') || '')),
  name: name,
  x: Math.round(r.left + window.pageXOffset),
  y: Math.round(r.top + window.pageYOffset),
  w: Math.round(r.width),
  h: Math.round(r.height),
  visivel: visible,
  habilitado: !(el.disabled === true),
  popup: el.getAttribute('aria-haspopup') || ''
};
"""

CHROME_BINARIES = (
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
)

# Sobrescritos em main() via argparse
NOME_ARQUIVO_JSON = DEFAULT_JSON
PASTA_SCREENS = DEFAULT_SCREENS

# Estado da varredura (evita retrabalho / dá progresso)
_visited_ids = set()
_extract_count = 0
_screens_ready = False


def reset_extract_state():
    global _visited_ids, _extract_count, _screens_ready
    _visited_ids = set()
    _extract_count = 0
    _screens_ready = False


def ensure_screens_dir():
    global _screens_ready
    if not _screens_ready:
        Path(PASTA_SCREENS).mkdir(parents=True, exist_ok=True)
        _screens_ready = True


def snapshot_element(driver, element):
    try:
        return driver.execute_script(JS_ELEMENT_SNAPSHOT, element)
    except StaleElementReferenceException:
        return None
    except Exception:
        return None


# ==============================================================================
# 🌐 DRIVER
# ==============================================================================

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


def get_driver():
    binary = find_chrome_binary()
    full_ver, major = detect_browser_version(binary) if binary else (None, None)

    options = Options()
    if binary:
        options.binary_location = binary
    options.add_argument("--no-sandbox")
    options.add_argument("--start-fullscreen")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")

    print(f"🌐 Browser: {binary or '(padrão)'} {full_ver or ''}".rstrip())

    try:
        driver = webdriver.Chrome(options=options)
        print("✅ Driver via Selenium Manager")
        ensure_fullscreen(driver)
        return driver
    except SessionNotCreatedException as e:
        print(f"⚠️ Selenium Manager incompatível: {str(e).splitlines()[0]}")
    except Exception as e:
        print(f"⚠️ Selenium Manager falhou: {e}")

    if not major:
        raise RuntimeError("Não foi possível detectar a versão do Chromium/Chrome.")

    print(f"⬇️ Baixando ChromeDriver major={major}...")
    driver_path = ChromeDriverManager(
        driver_version=major,
        chrome_type=ChromeType.CHROMIUM,
    ).install()
    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    ensure_fullscreen(driver)
    return driver


def ensure_fullscreen(driver):
    """Mantém a janela em tela cheia (não altera o tamanho do viewport)."""
    try:
        driver.fullscreen_window()
    except Exception:
        try:
            driver.maximize_window()
        except Exception:
            pass


# ==============================================================================
# 🧹 PREPARAÇÃO DA PÁGINA
# ==============================================================================

def dismiss_overlays(driver):
    """Fecha cookies, CEP e modais comuns (Americanas e genéricos)."""
    # Uma passagem via JS — bem mais rápida que N find_elements + click
    try:
        driver.execute_script("""
          const sels = [
            "button#onetrust-accept-btn-handler",
            "button[id*='accept']",
            "button[aria-label*='Aceitar' i]",
            "button[aria-label*='Fechar' i]",
            "button[aria-label*='Close' i]",
            "[data-testid='store-close-button']",
            "[data-testid='close-button']",
            "button.close",
            ".cookie-banner button"
          ];
          for (const s of sels) {
            document.querySelectorAll(s).forEach(b => {
              try { if (b && b.offsetParent !== null) b.click(); } catch (e) {}
            });
          }
        """)
    except Exception:
        pass

    try:
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    except Exception:
        pass


def scroll_to_load_lazy(driver, steps=3, pause=0.15):
    """Rola a página para disparar lazy-load de produtos/imagens."""
    try:
        height = driver.execute_script("return document.body.scrollHeight") or 0
        for i in range(1, steps + 1):
            driver.execute_script(
                "window.scrollTo(0, arguments[0]);",
                int(height * i / steps),
            )
            time.sleep(pause)
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass


def wait_page_ready(driver, url):
    """Espera conteúdo útil: produtos Americanas, MainDiv Limeira, ou body."""
    dismiss_overlays(driver)

    waiters = [
        (By.CSS_SELECTOR, "[data-testid*='product'], .product-grid, a[href*='/produto/']"),
        (By.ID, "MainDiv"),
        (By.ID, "__next"),
        (By.TAG_NAME, "body"),
    ]
    for by, sel in waiters:
        try:
            WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                EC.presence_of_element_located((by, sel))
            )
            print(f"✅ Página pronta ({sel})")
            break
        except TimeoutException:
            continue

    if "americanas.com" in url:
        scroll_to_load_lazy(driver)
        dismiss_overlays(driver)


def find_root_element(driver):
    for by, sel in (
        (By.ID, "MainDiv"),
        (By.ID, "__next"),
        (By.CSS_SELECTOR, "main"),
        (By.TAG_NAME, "body"),
    ):
        try:
            el = driver.find_element(by, sel)
            if el:
                return el
        except Exception:
            continue
    return driver.find_element(By.TAG_NAME, "body")


# ==============================================================================
# 🧠 EXTRAÇÃO
# ==============================================================================

def reset_mouse(driver):
    try:
        driver.execute_script(
            "document.dispatchEvent(new MouseEvent('mousemove', "
            "{clientX: 2, clientY: 2, bubbles: true}));"
        )
    except Exception:
        pass


def is_element_interactive(tag_name, class_name, popup=""):
    if tag_name in TAGS_INTERATIVAS_PADRAO:
        return True
    if popup in ("menu", "true", "listbox"):
        return True
    if class_name:
        for interactive_cls in FORCED_INTERACTIVE_CLASSES:
            if interactive_cls in class_name or class_name.startswith(interactive_cls):
                return True
        if "temp05" in class_name or "temp06" in class_name:
            return True
        # Só classes de trigger de menu (não main-header inteiro — muito largo)
        if any(k in class_name for k in ("MenuDesktop", "h-usr-link", "department-nav")):
            return True
    return False


def detect_dropdown(tag_name, class_name, popup=""):
    """Retorna (is_dropdown, action_type) com action_type in {click, hover}."""
    if tag_name == "select":
        return True, "click"
    if popup in ("menu", "true", "listbox"):
        return True, "hover"
    if class_name:
        if any(cls in class_name for cls in CUSTOM_DROPDOWN_CLASSES):
            return True, "click"
        if any(cls in class_name for cls in ("MenuDesktop", "h-usr-link", "department-nav")):
            return True, "hover"
    return False, "click"


def take_element_screenshot(element, level, tag_name, w, h):
    if w < SCREENSHOT_MIN_SIZE or h < SCREENSHOT_MIN_SIZE:
        return ""
    ensure_screens_dir()
    screenshot_filename = f"L{level}_{tag_name}_{int(time.time() * 1000)}.png"
    screenshot_path = Path(PASTA_SCREENS) / screenshot_filename
    try:
        element.screenshot(str(screenshot_path))
        return screenshot_filename
    except Exception:
        return ""


def build_node_from_snap(snap, level, action_type="click", is_dropdown=False, screenshot=""):
    tag = snap["tag"]
    return {
        "is_dropdown": is_dropdown,
        "nome": snap.get("name") or "",
        "classe": snap.get("className") or "",
        "tag": tag,
        "tipo_controle": (
            "CustomWidget" if "temp" in (snap.get("className") or "") else tag.capitalize()
        ),
        "nivel": level,
        "acao": action_type,
        "posicao": {
            "x": snap.get("x", 0),
            "y": snap.get("y", 0),
            "w": snap.get("w", 0),
            "h": snap.get("h", 0),
        },
        "visivel": bool(snap.get("visivel")),
        "habilitado": bool(snap.get("habilitado")),
        "id_automacao": snap.get("id") or "",
        "ignorado": not bool(snap.get("visivel")),
        "screenshot": screenshot,
        "filhos": [],
    }


def extract_leaf_fast(driver, element, level):
    """Lê item (ex.: submenu) sem abrir menus aninhados — bem mais rápido."""
    global _extract_count
    try:
        sid = element.id
        if sid in _visited_ids:
            return None
        _visited_ids.add(sid)
    except Exception:
        pass

    snap = snapshot_element(driver, element)
    if not snap:
        return None

    shot = ""
    if snap.get("visivel"):
        shot = take_element_screenshot(
            element, level, snap["tag"], snap.get("w", 0), snap.get("h", 0)
        )

    _extract_count += 1
    if _extract_count % PROGRESS_EVERY == 0:
        print(f"  … {_extract_count} componentes")

    return build_node_from_snap(snap, level, screenshot=shot)


def extract_element_data(element, level, driver, expand_menus=True):
    global _extract_count
    data = {}

    try:
        try:
            sid = element.id
            if sid in _visited_ids:
                return None
        except Exception:
            sid = None

        snap = snapshot_element(driver, element)
        if not snap:
            return None

        tag_name = snap["tag"]
        current_classes = snap.get("className") or ""
        popup = snap.get("popup") or ""
        element_name = snap.get("name") or ""

        if not element_name and ("temp05" in current_classes or "temp06" in current_classes):
            try:
                title_elem = element.find_element(By.CSS_SELECTOR, "[class*='titulo']")
                tsnap = snapshot_element(driver, title_elem)
                if tsnap:
                    element_name = tsnap.get("name") or ""
                    snap["name"] = element_name
            except Exception:
                pass

        if not is_element_interactive(tag_name, current_classes, popup):
            data["filhos"] = []
            try:
                children = element.find_elements(By.XPATH, "./*")
                for child in children:
                    child_data = extract_element_data(child, level, driver, expand_menus)
                    if child_data:
                        if isinstance(child_data, list):
                            data["filhos"].extend(child_data)
                        elif isinstance(child_data, dict):
                            data["filhos"].append(child_data)
            except StaleElementReferenceException:
                pass
            except Exception:
                pass
            return data["filhos"] if data["filhos"] else None

        if sid:
            _visited_ids.add(sid)

        is_dropdown_flag, action_type = detect_dropdown(tag_name, current_classes, popup)
        snap["name"] = element_name

        shot = ""
        if snap.get("visivel"):
            shot = take_element_screenshot(
                element, level, tag_name, snap.get("w", 0), snap.get("h", 0)
            )

        data = build_node_from_snap(
            snap, level, action_type=action_type, is_dropdown=is_dropdown_flag, screenshot=shot
        )

        _extract_count += 1
        if _extract_count % PROGRESS_EVERY == 0:
            print(f"  … {_extract_count} componentes")

        # Só expande menus no nível raiz (evita cascata infinita/lenta na Americanas)
        if expand_menus and is_dropdown_flag and data["visivel"] and level == 0:
            print(f" ↪️ Menu/Dropdown: '{data['nome'][:40]}' ({action_type})")
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'nearest', inline: 'nearest'});",
                    element,
                )

                if action_type == "hover":
                    ActionChains(driver).move_to_element(element).perform()
                    time.sleep(WAIT_TIME_MENU_OPEN)
                else:
                    if tag_name == "a":
                        driver.execute_script(
                            "arguments[0].setAttribute('data-href-backup', arguments[0].href || '');"
                            "arguments[0].removeAttribute('href');",
                            element,
                        )
                    driver.execute_script("arguments[0].click();", element)
                    time.sleep(WAIT_TIME_AFTER_CLICK)

                submenu_container = None
                try:
                    submenu_container = element.find_element(By.CSS_SELECTOR, ".menuDinamico")
                    if not submenu_container.is_displayed():
                        submenu_container = element.find_element(
                            By.XPATH,
                            "./following-sibling::*[contains(@class, 'menuDinamico')]",
                        )
                except Exception:
                    submenu_container = None

                if submenu_container is None or not submenu_container.is_displayed():
                    menus = driver.find_elements(
                        By.XPATH,
                        "//section[contains(@class, 'Menu')] "
                        "| //div[contains(@class, 'menuItemHovering')] "
                        "| //ul[contains(@class, 'dropdown')]",
                    )
                    for menu in menus:
                        try:
                            msnap = snapshot_element(driver, menu)
                            if (
                                msnap
                                and msnap.get("visivel")
                                and msnap.get("h", 0) > 20
                                and msnap.get("w", 0) > 20
                                and menu.id != element.id
                            ):
                                submenu_container = menu
                                break
                        except StaleElementReferenceException:
                            continue

                if submenu_container and submenu_container.is_displayed():
                    # Só links/botões diretos — leitura rápida sem reabrir menus
                    submenu_items = submenu_container.find_elements(
                        By.CSS_SELECTOR, "a, button"
                    )
                    seen = set()
                    for sub_item in submenu_items:
                        try:
                            leaf = extract_leaf_fast(driver, sub_item, level + 1)
                            if not leaf or not leaf.get("visivel"):
                                continue
                            key = (leaf.get("tag"), (leaf.get("nome") or "")[:40], leaf["posicao"]["x"], leaf["posicao"]["y"])
                            if key in seen:
                                continue
                            seen.add(key)
                            data["filhos"].append(leaf)
                        except StaleElementReferenceException:
                            continue
                    print(f" ✅ Itens extraídos: {len(data['filhos'])}")

                if action_type == "hover":
                    reset_mouse(driver)
                else:
                    try:
                        driver.execute_script("arguments[0].click();", element)
                    except Exception:
                        pass
                    if tag_name == "a":
                        try:
                            driver.execute_script(
                                "var h=arguments[0].getAttribute('data-href-backup');"
                                "if(h){arguments[0].setAttribute('href', h);}",
                                element,
                            )
                        except Exception:
                            pass

            except Exception as e:
                print(f" ⚠️ Erro ao interagir com menu: {e}")
                reset_mouse(driver)

    except StaleElementReferenceException:
        return None
    except Exception:
        return None

    return data


def normalize_ui_structure(ui_structure_data):
    """Garante lista plana de componentes no topo do JSON."""
    if ui_structure_data is None:
        return []
    if isinstance(ui_structure_data, list):
        return [n for n in ui_structure_data if isinstance(n, dict)]
    if isinstance(ui_structure_data, dict):
        filhos = ui_structure_data.get("filhos")
        if filhos and ui_structure_data.get("tag") not in TAGS_INTERATIVAS_PADRAO:
            return [n for n in filhos if isinstance(n, dict)]
        return [ui_structure_data]
    return []


def salvar_json_em_arquivo(data, nome_arquivo):
    path = Path(nome_arquivo)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"\n✅ JSON salvo em: {path.resolve()}")


def scrape_ui_structure(url):
    reset_extract_state()
    Path(PASTA_SCREENS).mkdir(parents=True, exist_ok=True)
    Path(NOME_ARQUIVO_JSON).parent.mkdir(parents=True, exist_ok=True)

    driver = get_driver()
    driver.set_page_load_timeout(60)

    try:
        print(f"🌐 Acessando {url}")
        ensure_fullscreen(driver)
        driver.get(url)
        ensure_fullscreen(driver)
        print("⏳ Aguardando carregamento...")
        time.sleep(TIME_TO_START)
        wait_page_ready(driver, url)
        ensure_fullscreen(driver)

        root_element = find_root_element(driver)
        print(f"🌳 Root: <{root_element.tag_name}> id={root_element.get_attribute('id') or '-'}")

        t0 = time.time()
        ui_structure_data = extract_element_data(root_element, 0, driver)
        ui_list = normalize_ui_structure(ui_structure_data)
        # Flatten filhos de menus no topo (mantém formato lista plana usado no anotador)
        flat = []
        for n in ui_list:
            if not isinstance(n, dict):
                continue
            filhos = n.get("filhos") or []
            n["filhos"] = []
            flat.append(n)
            for f in filhos:
                if isinstance(f, dict):
                    f = dict(f)
                    f["filhos"] = f.get("filhos") or []
                    flat.append(f)

        elapsed = time.time() - t0
        print(f"📦 Componentes extraídos: {len(flat)} em {elapsed:.1f}s")

        return {"ui_structure": flat}

    except Exception as e:
        print(f"❌ Erro fatal na extração: {e}")
        return None
    finally:
        driver.quit()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extrai estrutura UI (Limeira, Americanas e páginas similares)."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL da página a varrer")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_JSON),
        help="Caminho do JSON de saída",
    )
    parser.add_argument(
        "--screens",
        default=str(DEFAULT_SCREENS),
        help="Pasta de screenshots",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    NOME_ARQUIVO_JSON = Path(args.out)
    PASTA_SCREENS = Path(args.screens)
    if not NOME_ARQUIVO_JSON.is_absolute():
        NOME_ARQUIVO_JSON = BASE_DIR / NOME_ARQUIVO_JSON
    if not PASTA_SCREENS.is_absolute():
        PASTA_SCREENS = BASE_DIR / PASTA_SCREENS

    print(f"Iniciando varredura: {args.url}")
    print(f"📁 JSON → {NOME_ARQUIVO_JSON}")
    print(f"📁 Screens → {PASTA_SCREENS}")

    ui_json = scrape_ui_structure(args.url)
    if ui_json:
        salvar_json_em_arquivo(ui_json, NOME_ARQUIVO_JSON)
        print("✨ Processo finalizado.")
