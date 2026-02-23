import re

def build_context(window_info, raw_text, max_chars=4000):
    """
    Cleans and formats the context from window info and raw text.

    Args:
        window_info (dict): Info about the window (process_name, title, pid).
        raw_text (str): Raw extracted text from UIA.
        max_chars (int): Maximum characters for the final context string.

    Returns:
        str: Formatted and cleaned context string.
    """
    if not window_info:
        return "No active window context available."

    process_name = window_info.get("process_name", "Unknown")
    title = window_info.get("title", "Unknown")
    pid = window_info.get("pid", "Unknown")

    header = f"Process: {process_name} | Title: {title} | PID: {pid}\n"
    header += "-" * 50 + "\n"

    # Process raw text
    if not raw_text:
        cleaned_text = "(No text content extracted)"
    else:
        lines = raw_text.splitlines()
        seen_lines = set()
        clean_lines = []

        for line in lines:
            line = line.strip()
            # Remove garbage: too short
            if len(line) < 2:
                continue
            # Remove if only symbols (heuristic) - at least one alphanumeric char
            if not any(c.isalnum() for c in line):
                continue

            # Normalize spaces within the line
            line = re.sub(r'\s+', ' ', line)

            if line not in seen_lines:
                seen_lines.add(line)
                clean_lines.append(line)

        if not clean_lines:
             cleaned_text = "(No valid text content extracted)"
        else:
             cleaned_text = "\n".join(clean_lines)

    full_text = header + cleaned_text

    # Truncate if necessary
    if len(full_text) > max_chars:
        # Try to cut at last newline before max_chars to avoid cutting words
        truncated = full_text[:max_chars]
        last_newline = truncated.rfind('\n')

        # Ensure we don't cut off the header if the header is long or text is short
        if last_newline > len(header):
            full_text = truncated[:last_newline] + "\n... (truncated)"
        else:
            # Fallback: simple truncation
            full_text = truncated + "..."

    return full_text
