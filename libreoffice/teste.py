import json
import time
import threading
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from PIL import ImageGrab

# Dependências externas
try:
    from pywinauto import Application, Desktop
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto.keyboard import send_keys
except ImportError as e:
    print(f"❌ Erro de dependência: {e}")
    print("Instale via: pip install pywinauto pillow")
    exit(1)

# ============================================================
# CONFIGURAÇÃO E LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("extrator.log", encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# CLASSES DE CONFIGURAÇÃO (Baseado no anexo)
# ============================================================

@dataclass
class BanlistConfig:
    """Configuração do que deve ser ignorado durante a extração"""
    # Nomes exatos para ignorar (case-insensitive)
    nomes_exatos: Set[str] = field(default_factory=set)
    # Classes de UI para ignorar (ex: ToolTip, SysShadow)
    classes: Set[str] = field(default_factory=set)
    # Strings que, se estiverem no nome, causam o ignore (Use com cuidado)
    nomes_parciais: Set[str] = field(default_factory=set)

@dataclass
class ExtractorConfig:
    """Configuração geral da execução"""
    app_path: str
    output_file: str = "resultado_ui.json"
    use_multithreading: bool = False
    max_workers: int = 4
    take_screenshots: bool = True
    screenshot_dir: str = "screenshots"
    max_depth: int = 30
    connect_timeout: int = 10

# ============================================================
# CLASSE PRINCIPAL DE EXTRAÇÃO
# ============================================================

class UIExtractor:
    def __init__(self, config: ExtractorConfig, banlist: BanlistConfig):
        self.config = config
        self.banlist = banlist
        self.lock = threading.Lock() # Para thread-safety em screenshots e logs
        self.menus_visitados = set()
        
        # Cria diretório de screenshots se necessário
        if self.config.take_screenshots and not os.path.exists(self.config.screenshot_dir):
            os.makedirs(self.config.screenshot_dir)

    def _is_banned(self, element_name: str, element_class: str) -> bool:
        """Verifica se o elemento está na banlist"""
        name_clean = element_name.strip().lower()
        
        # 1. Verifica Classes proibidas
        if element_class in self.banlist.classes:
            return True

        # 2. Verifica Nomes Exatos
        if any(banned.lower() == name_clean for banned in self.banlist.nomes_exatos):
            return True

        # 3. Verifica Parciais (se configurado)
        if any(partial.lower() in name_clean for partial in self.banlist.nomes_parciais):
            return True

        return False

    def _capture_screenshot(self, element, prefix="elem") -> Optional[str]:
        """Captura screenshot de forma thread-safe"""
        if not self.config.take_screenshots:
            return None

        try:
            # Em multithreading, o acesso ao clipboard/tela pode conflitar
            with self.lock:
                rect = element.rectangle()
                if rect.width() <= 0 or rect.height() <= 0:
                    return None
                
                # Captura
                img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
                
                timestamp = int(time.time() * 1000)
                sanitized_name = str(prefix).replace(" ", "_").replace("/", "_")[:40]
                filename = f"{sanitized_name}_{timestamp}.png"
                path = os.path.join(self.config.screenshot_dir, filename)
                
                img.save(path)
                return filename
        except Exception as e:
            # Logs de erro de imagem podem ser ruidosos, mantemos debug
            logger.debug(f"Falha no screenshot: {e}")
            return None

    def _extract_properties(self, element, level: int) -> Dict[str, Any]:
        """Extrai dados brutos do elemento"""
        try:
            rect = element.rectangle()
            nome = element.window_text()
            classe = element.class_name()
            
            return {
                "nome": nome,
                "classe": classe,
                "tipo_controle": element.element_info.control_type,
                "nivel": level,
                "posicao": {
                    "x": rect.left, "y": rect.top, 
                    "w": rect.width(), "h": rect.height()
                },
                "visivel": element.is_visible(),
                "habilitado": element.is_enabled(),
                "id_automacao": getattr(element.element_info, "automation_id", None),
                "ignorado": False,
                "screenshot": None,
                "filhos": []
            }
        except Exception as e:
            return {"erro": str(e), "nome": "Elemento inacessível"}

    def _expand_menu(self, element) -> bool:
        """Tenta expandir menus usando múltiplas estratégias"""
        try:
            # Estratégia 1: Expand
            element.expand()
            time.sleep(0.5)
            return True
        except:
            pass

        try:
            # Estratégia 2: Invoke
            element.invoke()
            time.sleep(0.5)
            return True
        except:
            pass
        
        try:
            # Estratégia 3: Click Input (Mais invasivo, mas funciona no LibreOffice)
            element.click_input()
            time.sleep(0.5)
            return True
        except:
            pass

        return False

    def _is_menu_type(self, element, name: str) -> bool:
        """Detecta se é um menu baseando-se no tipo e nome"""
        tipo = element.element_info.control_type
        if tipo in ("MenuItem", "Menu", "MenuBar"):
            return True
        
        # Palavras-chave específicas do LibreOffice
        keywords = ["arquivo", "editar", "exibir", "inserir", "formatar", "ferramentas", "janela", "ajuda"]
        if any(k in name.lower() for k in keywords):
            return True
        
        return False

    def process_element(self, element, level: int) -> Optional[Dict]:
        """
        Lógica central de processamento de um nó (elemento).
        Esta função é recursiva e agnóstica a threads.
        """
        if level > self.config.max_depth:
            return None

        # 1. Extração Básica
        props = self._extract_properties(element, level)
        if "erro" in props:
            return props

        nome = props["nome"]
        classe = props["classe"]

        # 2. Verificação de Banlist
        if self._is_banned(nome, classe):
            logger.info(f"🚫 Banlist bloqueou: {nome} ({classe})")
            return None # Retorna None para podar este ramo da árvore

        # 3. Screenshot (Se visível)
        if props["visivel"]:
            props["screenshot"] = self._capture_screenshot(element, prefix=f"L{level}_{nome}")

        # 4. Lógica de Menu (Expansão)
        is_menu = self._is_menu_type(element, nome)
        
        # Lock para modificar a lista de visitados globalmente
        should_expand = False
        with self.lock:
            if is_menu and nome not in self.menus_visitados:
                should_expand = True
                self.menus_visitados.add(nome)

        if should_expand:
            logger.info(f"{'  '*level}📂 Expandindo menu: {nome}")
            expanded = self._expand_menu(element)
            if expanded:
                props["submenu_expandido"] = True
                # Captura screenshot do menu aberto
                props["screenshot_expandido"] = self._capture_screenshot(element, prefix=f"MENU_{nome}")

        # 5. Processamento dos Filhos
        try:
            children = element.children()
            
            if not children:
                return props

            # === DECISÃO: SINGLE OU MULTI THREAD ===
            # Só usamos multithreading se configurado E se não estivermos muito profundos (overhead)
            # E se tivermos filhos suficientes para justificar.
            if self.config.use_multithreading and level < 3 and len(children) > 1:
                props["filhos"] = self._process_children_multithread(children, level + 1)
            else:
                props["filhos"] = self._process_children_singlethread(children, level + 1)
                
        except Exception as e:
            props["erro_filhos"] = str(e)

        # Fecha menu se foi aberto (para limpar a tela)
        if props.get("submenu_expandido"):
            send_keys("{ESC}")
            time.sleep(0.2)

        return props

    def _process_children_singlethread(self, children, level) -> List[Dict]:
        results = []
        for child in children:
            res = self.process_element(child, level)
            if res:
                results.append(res)
        return results

    def _process_children_multithread(self, children, level) -> List[Dict]:
        results = []
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # Mapeia futuros
            future_to_child = {
                executor.submit(self.process_element, child, level): child 
                for child in children
            }
            
            for future in as_completed(future_to_child):
                try:
                    data = future.result()
                    if data:
                        results.append(data)
                except Exception as exc:
                    logger.error(f"Erro em thread filha: {exc}")
        return results

    def run(self):
        """Inicia o processo completo"""
        logger.info(f"🚀 Iniciando extração. App: {self.config.app_path}")
        logger.info(f"⚙️ Modo: {'Multi-thread' if self.config.use_multithreading else 'Single-thread'}")
        
        # 1. Iniciar/Conectar Aplicação
        try:
            app = Application(backend="uia").start(self.config.app_path, timeout=5)
        except Exception:
            logger.warning("Não conseguiu iniciar (pode já estar aberto). Tentando conectar...")
        
        time.sleep(5) # Aguarda carga inicial UI

        window = None
        for i in range(self.config.connect_timeout):
            try:
                # Tenta conectar à janela principal (regex genérico para LibreOffice)
                app = Application(backend="uia").connect(title_re=".*LibreOffice.*")
                window = app.top_window()
                logger.info(f"✅ Janela encontrada: {window.window_text()}")
                break
            except Exception:
                time.sleep(1)
        
        if not window:
            logger.error("❌ Falha crítica: Janela não encontrada.")
            return

        # 2. Executar Mapeamento
        start_time = time.time()
        
        # Captura tela cheia inicial
        if self.config.take_screenshots:
            self._capture_screenshot(window, prefix="FULL_WINDOW")

        structure = self.process_element(window, level=0)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 3. Salvar Resultado
        final_data = {
            "metadata": {
                "app": "LibreOffice",
                "duration_seconds": duration,
                "config": str(self.config),
                "banlist": str(self.banlist)
            },
            "ui_structure": structure
        }

        with open(self.config.output_file, "w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"🏁 Concluído em {duration:.2f}s. Arquivo salvo: {self.config.output_file}")

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    
    # 1. Configurar Banlist (O que você quer IGNORAR)
    minha_banlist = BanlistConfig(
        # Banir exatamente estes nomes (case-insensitive)
        nomes_exatos={
            "Barra de título", 
            "System", 
            "Fechar", 
            "Minimizar", 
            "Restaurar",
            "Aplicativo"
            "Arquivo",
            "Ajuda"
        },
        # Banir classes inteiras (Elementos técnicos do Windows)
        classes={
            "SysShadow", 
            "ToolTip",
            "MSCTFIME UI" # Interface de input method do Windows
        },
        # Banir elementos que contenham este texto (CUIDADO: Pode banir demais)
        nomes_parciais={
            "Novo",
            "Arquivo",
            "Ajuda",
            # "ajuda"  <-- Exemplo: descomente para banir qualquer coisa com "ajuda" no nome
        }
    )

    # 2. Configurar Extração
    configuracao = ExtractorConfig(
        app_path=r"C:\Program Files\LibreOffice\program\swriter.exe", # <--- VERIFIQUE SEU CAMINHO
        output_file="resultado_libreoffice_avancado.json",
        
        # --- SELETOR DE THREADING ---
        use_multithreading=False,  # True = Rápido (Paralelo) | False = Estável (Linear)
        max_workers=4,            # Número de threads paralelas
        
        take_screenshots=True,    # Salvar imagens?
        screenshot_dir="imgs_lo_avancado"
    )

    # 3. Executar
    extractor = UIExtractor(configuracao, minha_banlist)
    extractor.run()