import logging
import psutil

# Configure logging
logger = logging.getLogger(__name__)

# Try to import Windows-specific libraries
try:
    import win32gui
    import win32process
    from pywinauto import Application
except ImportError:
    logger.warning("Windows libraries not found. This module will not function correctly without mocks.")
    win32gui = None
    win32process = None
    Application = None


def get_active_window_info():
    """
    Retrieves information about the currently active window.
    Returns:
        dict: {"hwnd": int, "title": str, "pid": int, "process_name": str}
    """
    if not win32gui:
        logger.error("win32gui not available.")
        return None

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            logger.error("No active window found (hwnd=0).")
            return None

        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        try:
            process = psutil.Process(pid)
            process_name = process.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            process_name = "Unknown"

        return {
            "hwnd": hwnd,
            "title": title,
            "pid": pid,
            "process_name": process_name
        }
    except Exception as e:
        logger.exception(f"Error getting active window info: {e}")
        return None


def list_open_windows():
    """
    Enumerates all visible windows.
    Returns:
        list: List of dicts {"hwnd": int, "title": str, "process_name": str}
    """
    if not win32gui:
        logger.error("win32gui not available.")
        return []

    windows = []

    def enum_handler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    try:
                        proc = psutil.Process(pid)
                        proc_name = proc.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        proc_name = "Unknown"

                    windows.append({
                        "hwnd": hwnd,
                        "title": title,
                        "process_name": proc_name,
                        "pid": pid
                    })
                except Exception:
                    pass

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception as e:
        logger.error(f"Error enumerating windows: {e}")

    return windows


def extract_text_uia(hwnd):
    """
    Extracts text from the window with the given hwnd using UI Automation.
    Args:
        hwnd (int): Window handle.
    Returns:
        str: Extracted text joined by newlines.
    """
    if not Application:
        logger.error("pywinauto not available.")
        return ""

    extracted_texts = []
    seen_texts = set()
    total_chars = 0
    MAX_UIA_CHARS = 12000

    try:
        # Connect to the application
        # timeout is important to avoid hanging
        app = Application(backend="uia").connect(handle=hwnd, timeout=5)

        # Get the window wrapper
        top_node = app.window(handle=hwnd).wrapper_object()

        # Helper to extract text from a single element
        def get_element_text(elem):
            texts = []

            # 1. Window Text / Name
            try:
                t1 = elem.window_text()
                if t1:
                    texts.append(t1)
            except Exception:
                pass

            # 2. Value Pattern via Legacy Properties (most reliable common fallback)
            try:
                props = elem.legacy_properties()
                if props and 'Value' in props and props['Value']:
                     val = str(props['Value'])
                     if val and val not in texts:
                         texts.append(val)
            except Exception:
                pass

            # 3. Text Pattern (Simpler approach: if 'Value' attribute exists directly)
            # Some controls expose 'texts' method in pywinauto
            try:
                if hasattr(elem, 'texts'):
                    t_list = elem.texts()
                    for t in t_list:
                        if t and len(t) > 0:
                            # Usually texts() returns list of strings
                            if isinstance(t, str) and t not in texts:
                                texts.append(t)
                            elif isinstance(t, list): # recursive
                                for sub_t in t:
                                    if sub_t and sub_t not in texts:
                                        texts.append(sub_t)
            except Exception:
                pass

            return " ".join(texts).strip()

        # Walk descendants
        # We fetch descendants once. This can be slow for very complex UIs.
        descendants = top_node.descendants()

        # Try to find focused element among descendants (simulated)
        # Real UIA has GetFocusedElement but pywinauto exposes it differently.
        # We'll just iterate order of descendants which is usually DFS.

        for child in descendants:
            if total_chars >= MAX_UIA_CHARS:
                break

            try:
                if not child.is_visible():
                    continue

                text = get_element_text(child)

                # Filter empty or very short strings (noise)
                if not text or len(text.strip()) < 2:
                    continue

                # Filter 'Pane' controls that just return their generic name or no text
                # Often Panes have text="" or text="Pane"
                if child.friendly_class_name() == "Pane" and (text == "Pane" or text == ""):
                    continue

                if text not in seen_texts:
                    seen_texts.add(text)
                    extracted_texts.append(text)
                    total_chars += len(text)

            except Exception:
                continue

    except Exception as e:
        logger.error(f"Error extracting text via UIA: {e}")
        return ""

    return "\n".join(extracted_texts)
