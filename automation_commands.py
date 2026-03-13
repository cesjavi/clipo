import re
import unicodedata
from memory_manager import memory_manager


BROWSER_PROCESSES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "iexplore.exe",
}

CHROMIUM_PROCESSES = {
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "opera.exe",
}

MESSAGING_APPS = {
    "whatsapp.exe": "WhatsApp",
    "teams.exe": "Teams",
    "ms-teams.exe": "Teams",
    "discord.exe": "Discord",
}

MEDIA_APPS = {
    "spotify.exe": "Spotify",
}

SHELL_PROCESSES = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "windowsterminal.exe",
    "wt.exe",
}

SEARCH_SHORTCUTS = {
    "teams.exe": "^e",
    "ms-teams.exe": "^e",
    "discord.exe": "^k",
    "whatsapp.exe": "^k",
}

APP_ALIASES = {
    "navegador": "browser",
    "browser": "browser",
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
    "brave": "brave.exe",
    "opera": "opera.exe",
    "explorador": "explorer.exe",
    "explorer": "explorer.exe",
    "whatsapp": "whatsapp.exe",
    "teams": "teams.exe",
    "discord": "discord.exe",
    "youtube": "youtube",
}

KEY_MAPPINGS = {
    "enter": "{ENTER}",
    "intro": "{ENTER}",
    "tab": "{TAB}",
    "tabulador": "{TAB}",
    "esc": "{ESC}",
    "escape": "{ESC}",
    "espacio": "{SPACE}",
    "borrar": "{BACKSPACE}",
    "backspace": "{BACKSPACE}",
    "suprimir": "{DELETE}",
    "delete": "{DELETE}",
    "inicio": "{HOME}",
    "fin": "{END}",
    "insert": "{INSERT}",
    "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}", "f5": "{F5}",
    "f6": "{F6}", "f7": "{F7}", "f8": "{F8}", "f9": "{F9}", "f10": "{F10}",
    "f11": "{F11}", "f12": "{F12}",
    "arriba": "{UP}",
    "abajo": "{DOWN}",
    "izquierda": "{LEFT}",
    "derecha": "{RIGHT}",
    "re pag": "{PGUP}",
    "av pag": "{PGDN}",
}

AUTOMATION_PREFIXES = (
    "clipo",
    "quiero",
    "necesito",
    "podrias",
    "podrias por favor",
    "podes",
    "por favor",
    "cambiar",
    "ir a",
    "abrir",
    "seleccionar",
    "pestana",
    "tab",
    "mensaje",
    "mandar mensaje",
    "enviar mensaje",
    "escribir en el chat",
    "escribir al chat",
    "enviar al chat",
    "manda al chat",
    "chat ",
    "buscar chat",
    "escribe",
    "escribir",
    "tipea",
    "tipear",
    "presiona",
    "apreta",
    "youtube",
    "play",
    "pause",
    "reproducir",
    "reproduce",
    "parar",
    "detener",
    "poner",
    "pone",
    "dar play",
    "darle play",
    "activar",
    "ejecutar",
    "mute",
    "silenciar",
    "mutear",
    "activar microfono",
    "ensordecer",
    "siguiente cancion",
    "siguiente tema",
    "proxima cancion",
    "proximo tema",
    "cancion anterior",
    "tema anterior",
    "haga",
    "haz",
    "enfocar",
    "enfoca",
    "enfoga",
    "enfogar",
    "focalizar",
    "poner",
    "pone",
    "seleccionar ventana",
    "buscar",
    "busca",
    "computadora",
)


def normalize_command(command):
    return re.sub(r"\s+", " ", (command or "").strip())


def strip_conversational_prefix(command):
    text = normalize_command(command)
    patterns = (
        r"^(?:clipo(?:\s+hacer|\s+hace)?\s+)",
        r"^(?:quiero(?:\s+que)?\s+)",
        r"^(?:necesito(?:\s+que)?\s+)",
        r"^(?:podrias(?:\s+por\s+favor)?\s+)",
        r"^(?:podes\s+)",
        r"^(?:por\s+favor\s+)",
    )
    changed = True
    while changed and text:
        changed = False
        for pattern in patterns:
            updated = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()
            if updated != text:
                text = updated
                changed = True
    return normalize_command(text)


def fold_text(value):
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def detect_window_kind(window_info):
    if not window_info:
        return "generic"
    process_name = fold_text(window_info.get("process_name") or "")
    title = fold_text(window_info.get("title") or "")

    if process_name in SHELL_PROCESSES or "powershell" in title or "cmd.exe" in title:
        return "shell"
    if "youtube" in title and process_name in BROWSER_PROCESSES:
        return "youtube"
    if process_name in MEDIA_APPS or "spotify" in title:
        return "media"
    if process_name in MESSAGING_APPS or "whatsapp" in title or "teams" in title or "discord" in title:
        return "messaging"
    if process_name in BROWSER_PROCESSES:
        return "browser"
    if process_name == "explorer.exe":
        return "explorer"
    return "generic"


def parse_command(command, window_info, available_windows=None):
    normalized = strip_conversational_prefix(command)
    lowered = fold_text(normalized)
    available_windows = available_windows or []
    kind = detect_window_kind(window_info)
    process_name = fold_text(window_info.get("process_name") or "") if window_info else ""

    switch_action = _parse_switch_command(normalized, lowered, available_windows)
    if switch_action:
        return switch_action

    direct_message = _parse_direct_message_command(normalized, lowered, process_name)
    if direct_message:
        return direct_message

    write_action = _parse_write_text_command(normalized, lowered)
    if write_action:
        return write_action

    if kind == "shell":
        shell_action = _parse_shell_command(normalized, lowered)
        if shell_action:
            return shell_action

    chat_write_action = _parse_chat_write_command(normalized, lowered, process_name)
    if chat_write_action:
        return chat_write_action

    search_target = _parse_named_target_command(normalized, lowered, kind, process_name)
    if search_target:
        return search_target

    tab_action = _parse_tab_command(lowered)
    if tab_action:
        return tab_action

    if kind == "youtube":
        youtube_action = _parse_youtube_command(lowered)
        if youtube_action:
            return youtube_action

    if kind == "media":
        media_action = _parse_media_command(lowered, process_name)
        if media_action:
            return media_action

    conference_action = _parse_conference_command(lowered, process_name)
    if conference_action:
        return conference_action

    if kind == "messaging":
        message_action = _parse_message_command(normalized)
        if message_action:
            return message_action

    return {"type": "text", "text": normalized, "press_enter": True, "description": f"Texto: {normalized}"}


def looks_like_automation_command(command):
    text = strip_conversational_prefix(command)
    # Strip leading punctuation/symbols like ¡ or ¿
    text = re.sub(r'^[^a-zA-Z0-9]+', '', text)
    lowered = fold_text(text)
    return any(lowered.startswith(prefix) for prefix in AUTOMATION_PREFIXES)


def _parse_switch_command(normalized, lowered, available_windows):
    patterns = (
        r"^(?:cambiar|ir)(?:\s+a| al)?(?:\s+la\s+ventana|la\s+app|el\s+programa)?\s+(.+)$",
        r"^(?:abrir|seleccionar|enfocar|enfoca|enfogar|enfoga|poner|pone)(?:\s+la\s+ventana|la\s+app|el\s+programa)?\s+(.+)$",
    )
    target = None
    for pattern in patterns:
        match = re.match(pattern, lowered)
        if match:
            target = match.group(1).strip()
            break

    if not target:
        return None

    target_tokens = target.split()
    if len(target_tokens) >= 2 and target_tokens[0] in {"pestana", "tab"} and target_tokens[1].isdigit():
        return _build_tab_index_action(target_tokens[1])

    resolved = resolve_window_target(target, available_windows)
    if resolved:
        return {
            "type": "switch_window",
            "target_hwnd": resolved["hwnd"],
            "description": f"Cambiar a {resolved['title']}",
        }
    
    # If the user used a clear switch verb but we didn't find the window,
    # let's return a special error or description so we don't fall back to "writing text".
    if re.match(r"^(?:abrir|seleccionar|enfocar|enfoca|enfogar|enfoga|poner|pone)", lowered):
         return {
            "type": "switch_window", # We use switch_window type to bypass the "need window" error
            "target_hwnd": None, 
            "description": f"No se encontró ninguna ventana que coincida con '{target}'",
            "error": True
        }
    return None


def _parse_direct_message_command(normalized, lowered, process_name):
    match = re.match(r"^(?:mensaje|mandar mensaje|enviar mensaje)\s+a\s+(.+?)\s+(.+)$", lowered)
    if not match:
        return None

    target = match.group(1).strip()
    original_match = re.match(r"^(?:mensaje|mandar mensaje|enviar mensaje)\s+a\s+(.+?)\s+(.+)$", normalized, re.IGNORECASE)
    message = original_match.group(2).strip() if original_match else normalized
    search_keys = SEARCH_SHORTCUTS.get(process_name)
    if not search_keys:
        return None

    return {
        "type": "search_and_send",
        "search_keys": search_keys,
        "target": target,
        "text": _clean_spoken_message(message),
        "description": f"Abrir {target} y enviar mensaje",
    }


def _parse_chat_write_command(normalized, lowered, process_name):
    search_keys = SEARCH_SHORTCUTS.get(process_name)
    if not search_keys:
        return None

    targeted_patterns = (
        r"^(?:escribir|escribe|enviar|manda|mandar)\s+en\s+el\s+chat\s+de\s+(.+?)\s+lo\s+siguiente[:,]?\s*(.+)$",
        r"^(?:escribir|escribe|enviar|manda|mandar)\s+al\s+chat\s+de\s+(.+?)\s+lo\s+siguiente[:,]?\s*(.+)$",
        r"^(?:escribir|escribe|enviar|manda|mandar)\s+en\s+el\s+chat\s+de\s+(.+?)\s*[:,-]\s*(.+)$",
        r"^(?:escribir|escribe|enviar|manda|mandar)\s+al\s+chat\s+de\s+(.+?)\s*[:,-]\s*(.+)$",
    )
    for pattern in targeted_patterns:
        lowered_match = re.match(pattern, lowered)
        original_match = re.match(pattern, normalized, re.IGNORECASE)
        if lowered_match and original_match:
            return {
                "type": "search_and_send",
                "search_keys": search_keys,
                "target": lowered_match.group(1).strip(),
                "text": _clean_spoken_message(original_match.group(2).strip()),
                "description": f"Abrir {lowered_match.group(1).strip()} y enviar mensaje",
            }

    current_chat_patterns = (
        r"^(?:escribir|escribe|enviar|manda|mandar)\s+en\s+el\s+chat\s+(?:lo\s+siguiente[:,]?\s*)?(.+)$",
        r"^(?:escribir|escribe|enviar|manda|mandar)\s+al\s+chat\s+(?:lo\s+siguiente[:,]?\s*)?(.+)$",
    )
    for pattern in current_chat_patterns:
        original_match = re.match(pattern, normalized, re.IGNORECASE)
        if original_match:
            message = _clean_spoken_message(original_match.group(1).strip())
            return {
                "type": "text",
                "text": message,
                "press_enter": True,
                "description": f"Mensaje: {message}",
            }

    return None


def _parse_write_text_command(normalized, lowered):
    quoted_match = re.match(
        r"^(?:escribir|escribe|tipear|tipea)\s+[\"'“”]?(.+?)[\"'“”]?\s*(?:y\s+)?(?:apreta|presiona)(?:\s+la\s+tecla\s+|\s+tecla\s+|\s+)?enter$",
        normalized,
        re.IGNORECASE,
    )
    if quoted_match:
        text = _clean_spoken_message(quoted_match.group(1).strip())
        return {
            "type": "text",
            "text": text,
            "press_enter": True,
            "description": f"Escribir texto y apretar Enter: {text}",
        }

    no_enter_match = re.match(
        r"^(?:escribir|escribe|tipear|tipea)\s+[\"'“”]?(.+?)[\"'“”]?$",
        normalized,
        re.IGNORECASE,
    )
    if no_enter_match:
        text = _clean_spoken_message(no_enter_match.group(1).strip())
        lowered_text = fold_text(text)
        if lowered_text not in {"enter", "intro"}:
            return {
                "type": "text",
                "text": text,
                "press_enter": False,
                "description": f"Escribir texto: {text}",
            }

    key_match = re.match(
        r"^(?:apreta|presiona|apretar|presionar|precionar|abretar|cliquea|pulsionar)(?:\s+la)?(?:\s+tecla)?\s+(.+)$",
        lowered,
    )
    if key_match:
        target_key = key_match.group(1).strip(" .,:;!?")
        if target_key in KEY_MAPPINGS:
            return {
                "type": "shortcut",
                "keys": KEY_MAPPINGS[target_key],
                "description": f"Apretar tecla {target_key}",
            }

    return None


def _parse_shell_command(normalized, lowered):
    cleaned = lowered.strip(" .,:;!?")

    list_files_commands = {
        "listar archivos",
        "listar los archivos",
        "listar los archivos que hay",
        "lista los archivos",
        "lista los archivos que hay",
        "mostrar archivos",
        "mostrar los archivos",
        "mostrar los archivos que hay",
        "mostra los archivos",
        "mostra los archivos que hay",
        "ver archivos",
        "ver los archivos",
        "ver los archivos que hay",
    }
    if cleaned in list_files_commands:
        return {
            "type": "text",
            "text": "dir",
            "press_enter": True,
            "description": "Listar archivos del directorio actual",
        }

    if cleaned in {"mostrar carpeta actual", "mostrar directorio actual", "ver carpeta actual", "ver directorio actual"}:
        return {
            "type": "text",
            "text": "cd",
            "press_enter": True,
            "description": "Mostrar directorio actual",
        }

    mkdir_match = re.match(
        r"^(?:crear|crea|criar|hace|hacer)\s+(?:un\s+|una\s+)?(?:directorio|carpeta|folder)(?:\s+llamad[oa])?\s+(.+)$",
        normalized,
        re.IGNORECASE,
    )
    if mkdir_match:
        directory_name = mkdir_match.group(1).strip().strip('"').strip(".")
        if directory_name:
            return {
                "type": "text",
                "text": f'mkdir "{directory_name}"',
                "press_enter": True,
                "description": f"Crear directorio {directory_name}",
            }

    match = re.match(
        r"^(?:cambiar|ir)(?:\s+a)?\s+(?:la\s+carpeta|al\s+directorio|al\s+folder|a\s+la\s+ruta)\s+(.+)$",
        normalized,
        re.IGNORECASE,
    )
    if match:
        target = match.group(1).strip().strip('"')
        return {
            "type": "text",
            "text": f'cd /d "{target}"',
            "press_enter": True,
            "description": f"Cambiar al directorio {target}",
        }

    return None


def _parse_named_target_command(normalized, lowered, kind, process_name):
    match = re.match(r"^(?:ir a )?(?:pestana|tab)\s+(.+)$", lowered)
    if match:
        name = match.group(1).strip()
        if name in {
            "siguiente",
            "anterior",
            "nueva",
            "cerrar",
            "reabrir",
            "ultima",
        }:
            return None
        if name.isdigit():
            return _build_tab_index_action(name)
        if kind == "browser" and process_name in CHROMIUM_PROCESSES:
            return {
                "type": "search_target",
                "search_keys": "^+a",
                "target": name,
                "description": f"Buscar pestaña {name}",
            }
        if kind == "messaging" and process_name in SEARCH_SHORTCUTS:
            return {
                "type": "search_target",
                "search_keys": SEARCH_SHORTCUTS[process_name],
                "target": name,
                "description": f"Buscar chat {name}",
            }

    chat_match = re.match(r"^(?:chat|abrir chat|buscar chat|seleccionar chat|buscar|busca)\s+(.+)$", lowered)
    if chat_match and process_name in SEARCH_SHORTCUTS:
        return {
            "type": "search_target",
            "search_keys": SEARCH_SHORTCUTS[process_name],
            "target": chat_match.group(1).strip(),
            "description": f"Buscar chat {chat_match.group(1).strip()}",
        }

    return None


def _parse_tab_command(lowered):
    direct_mappings = {
        "tab siguiente": {"type": "shortcut", "keys": "^{TAB}", "description": "Tab siguiente"},
        "siguiente tab": {"type": "shortcut", "keys": "^{TAB}", "description": "Tab siguiente"},
        "siguiente pestana": {"type": "shortcut", "keys": "^{TAB}", "description": "Tab siguiente"},
        "pestana siguiente": {"type": "shortcut", "keys": "^{TAB}", "description": "Tab siguiente"},
        "tab anterior": {"type": "shortcut", "keys": "^+{TAB}", "description": "Tab anterior"},
        "anterior tab": {"type": "shortcut", "keys": "^+{TAB}", "description": "Tab anterior"},
        "pestana anterior": {"type": "shortcut", "keys": "^+{TAB}", "description": "Tab anterior"},
        "anterior pestana": {"type": "shortcut", "keys": "^+{TAB}", "description": "Tab anterior"},
        "cerrar tab": {"type": "shortcut", "keys": "^w", "description": "Cerrar tab"},
        "cerrar pestana": {"type": "shortcut", "keys": "^w", "description": "Cerrar tab"},
        "nueva tab": {"type": "shortcut", "keys": "^t", "description": "Nueva tab"},
        "nueva pestana": {"type": "shortcut", "keys": "^t", "description": "Nueva tab"},
        "reabrir tab": {"type": "shortcut", "keys": "^+t", "description": "Reabrir tab"},
        "reabrir pestana": {"type": "shortcut", "keys": "^+t", "description": "Reabrir tab"},
        "ultima pestana": {"type": "shortcut", "keys": "^9", "description": "Ir a la última pestaña"},
        "ultima tab": {"type": "shortcut", "keys": "^9", "description": "Ir a la última pestaña"},
    }
    if lowered in direct_mappings:
        return direct_mappings[lowered]

    match = re.match(r"^(?:ir a )?(?:pestana|tab)\s+(\d+)$", lowered)
    if match:
        return _build_tab_index_action(match.group(1))

    return None


def _build_tab_index_action(index_text):
    try:
        index = int(index_text)
    except ValueError:
        return None
    if index < 1:
        return None
    key = "^9" if index >= 9 else f"^{index}"
    return {"type": "shortcut", "keys": key, "description": f"Ir a pestaña {index}"}


def _parse_youtube_command(lowered):
    youtube_commands = {
        "youtube play": {"type": "shortcut", "keys": "k", "description": "YouTube play"},
        "youtube pause": {"type": "shortcut", "keys": "k", "description": "YouTube pause"},
        "youtube play pause": {"type": "shortcut", "keys": "k", "description": "YouTube play/pause"},
        "play": {"type": "shortcut", "keys": "k", "description": "YouTube play"},
        "pause": {"type": "shortcut", "keys": "k", "description": "YouTube pause"},
        "reproducir": {"type": "shortcut", "keys": "k", "description": "YouTube reproducir"},
        "reproduce": {"type": "shortcut", "keys": "k", "description": "YouTube reproducir"},
        "parar": {"type": "shortcut", "keys": "k", "description": "YouTube pausar"},
        "detener": {"type": "shortcut", "keys": "k", "description": "YouTube pausar"},
        "pausar": {"type": "shortcut", "keys": "k", "description": "YouTube pausar"},
        "poner": {"type": "shortcut", "keys": "k", "description": "YouTube reproducir"},
        "pone": {"type": "shortcut", "keys": "k", "description": "YouTube reproducir"},
        "dar play": {"type": "shortcut", "keys": "k", "description": "YouTube play"},
        "darle play": {"type": "shortcut", "keys": "k", "description": "YouTube play"},
        "activar": {"type": "shortcut", "keys": "k", "description": "YouTube play"},
        "ejecutar": {"type": "shortcut", "keys": "k", "description": "YouTube play"},
        "youtube mute": {"type": "shortcut", "keys": "m", "description": "YouTube mute"},
        "mute": {"type": "shortcut", "keys": "m", "description": "YouTube mute"},
        "youtube fullscreen": {"type": "shortcut", "keys": "f", "description": "YouTube fullscreen"},
        "pantalla completa": {"type": "shortcut", "keys": "f", "description": "YouTube fullscreen"},
        "youtube subtitulos": {"type": "shortcut", "keys": "c", "description": "YouTube subtítulos"},
        "subtitulos": {"type": "shortcut", "keys": "c", "description": "YouTube subtítulos"},
        "youtube adelante": {"type": "shortcut", "keys": "l", "description": "YouTube adelante 10s"},
        "adelante": {"type": "shortcut", "keys": "l", "description": "YouTube adelante 10s"},
        "youtube atras": {"type": "shortcut", "keys": "j", "description": "YouTube atrás 10s"},
        "atras": {"type": "shortcut", "keys": "j", "description": "YouTube atrás 10s"},
        "siguiente cancion": {"type": "shortcut", "keys": "n", "description": "YouTube siguiente canción"},
        "siguiente tema": {"type": "shortcut", "keys": "n", "description": "YouTube siguiente canción"},
        "proxima cancion": {"type": "shortcut", "keys": "n", "description": "YouTube siguiente canción"},
        "proximo tema": {"type": "shortcut", "keys": "n", "description": "YouTube siguiente canción"},
        "cancion anterior": {"type": "shortcut", "keys": "p", "description": "YouTube canción anterior"},
        "tema anterior": {"type": "shortcut", "keys": "p", "description": "YouTube canción anterior"},
    }
    return youtube_commands.get(lowered)


def _parse_media_command(lowered, process_name):
    if process_name != "spotify.exe":
        return None

    spotify_commands = {
        "siguiente cancion": {"type": "shortcut", "keys": "^{RIGHT}", "description": "Spotify siguiente canción"},
        "siguiente tema": {"type": "shortcut", "keys": "^{RIGHT}", "description": "Spotify siguiente canción"},
        "cancion anterior": {"type": "shortcut", "keys": "^{LEFT}", "description": "Spotify canción anterior"},
        "tema anterior": {"type": "shortcut", "keys": "^{LEFT}", "description": "Spotify canción anterior"},
        "play": {"type": "shortcut", "keys": "{SPACE}", "description": "Spotify play/pause"},
        "pause": {"type": "shortcut", "keys": "{SPACE}", "description": "Spotify play/pause"},
        "play pause": {"type": "shortcut", "keys": "{SPACE}", "description": "Spotify play/pause"},
    }
    return spotify_commands.get(lowered)


def _parse_conference_command(lowered, process_name):
    mute_commands = {
        "silenciar": {"type": "shortcut", "keys": "^+m", "description": "Silenciar micrófono"},
        "activar microfono": {"type": "shortcut", "keys": "^+m", "description": "Activar/silenciar micrófono"},
        "mutear": {"type": "shortcut", "keys": "^+m", "description": "Silenciar micrófono"},
    }
    if process_name in {"teams.exe", "ms-teams.exe", "discord.exe"} and lowered in mute_commands:
        return mute_commands[lowered]

    if process_name == "discord.exe":
        discord_commands = {
            "ensordecer": {"type": "shortcut", "keys": "^+d", "description": "Discord ensordecer"},
            "quitar ensordecer": {"type": "shortcut", "keys": "^+d", "description": "Discord ensordecer"},
        }
        return discord_commands.get(lowered)

    return None


def _parse_message_command(normalized):
    lowered = fold_text(normalized)
    prefixes = (
        "mensaje ",
        "enviar mensaje ",
        "mandar mensaje ",
        "whatsapp ",
        "teams ",
        "discord ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            message = normalized[len(prefix):].strip()
            if message:
                return {
                    "type": "text",
                    "text": _clean_spoken_message(message),
                    "press_enter": True,
                    "description": f"Mensaje: {message}",
                }
    return None


def _clean_spoken_message(message):
    text = normalize_command(message)
    replacements = [
        (r"\bdos puntos\b", ":"),
        (r"\bpunto y coma\b", ";"),
        (r"\bcoma\b", ","),
        (r"\bpunto\b", "."),
        (r"\babro comillas\b", '"'),
        (r"\bcierro comillas\b", '"'),
        (r"\babrir comillas\b", '"'),
        (r"\bcerrar comillas\b", '"'),
        (r"\bsigno de pregunta\b", "?"),
        (r"\babrir parentesis\b", "("),
        (r"\bcerrar parentesis\b", ")"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    text = re.sub(r"\s+([,.:;?!])", r"\1", text)
    text = re.sub(r'"\s+', '"', text)
    text = re.sub(r'\s+"', '"', text)
    return normalize_command(text)


def resolve_window_target(target, available_windows):
    folded_target = fold_text(target).strip(" .,:;!?")
    
    # 0. Try learned aliases from memory first
    learned_aliases = memory_manager.memory.get("aliases", {})
    if folded_target in learned_aliases:
        found = _find_window_by_alias(learned_aliases[folded_target], available_windows)
        if found:
            return found

    # 1. Try hardcoded aliases
    for alias, resolved in APP_ALIASES.items():
        if folded_target == alias:
            found = _find_window_by_alias(resolved, available_windows)
            if found:
                return found

    # 2. Try partial title match (case-insensitive via fold_text)
    for window in available_windows:
        title = fold_text(window.get("title") or "")
        if folded_target and (folded_target in title or title in folded_target):
            return window
            
    # 3. Try partial process name match
    for window in available_windows:
        process_name = fold_text(window.get("process_name") or "")
        if folded_target and (folded_target in process_name or process_name in folded_target):
            return window

    return None


def _find_window_by_alias(alias, available_windows):
    if alias == "browser":
        for window in available_windows:
            if fold_text(window.get("process_name") or "") in BROWSER_PROCESSES:
                return window
        return None

    if alias == "youtube":
        for window in available_windows:
            process_name = fold_text(window.get("process_name") or "")
            title = fold_text(window.get("title") or "")
            if process_name in BROWSER_PROCESSES and "youtube" in title:
                return window
        return None

    for window in available_windows:
        if fold_text(window.get("process_name") or "") == alias:
            return window
    return None


def execute_parsed_command(window_info, parsed_command, automation):
    if parsed_command["type"] == "switch_window":
        if parsed_command.get("error"):
            # If it's a failed resolution, we don't switch, just return the description
            return parsed_command["description"]
        automation["switch_window"](parsed_command["target_hwnd"])
        return parsed_command["description"]

    hwnd = window_info["hwnd"]
    automation["focus"](hwnd)

    if parsed_command["type"] == "shortcut":
        automation["send_keys"](parsed_command["keys"])
    elif parsed_command["type"] == "text":
        automation["send_text"](parsed_command["text"])
        if parsed_command.get("press_enter", True):
            automation["send_keys"]("{ENTER}")
    elif parsed_command["type"] == "search_target":
        automation["send_keys"](parsed_command["search_keys"])
        automation["wait"](0.25)
        automation["send_text"](parsed_command["target"])
        automation["wait"](0.15)
        automation["send_keys"]("{ENTER}")
    elif parsed_command["type"] == "search_and_send":
        automation["send_keys"](parsed_command["search_keys"])
        automation["wait"](0.25)
        automation["send_text"](parsed_command["target"])
        automation["wait"](0.15)
        automation["send_keys"]("{ENTER}")
        automation["wait"](0.35)
        automation["send_text"](parsed_command["text"])
        automation["send_keys"]("{ENTER}")
    else:
        raise ValueError(f"Unsupported command type: {parsed_command['type']}")

    return parsed_command["description"]
