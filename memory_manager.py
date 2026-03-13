import json
import os
import logging

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self, filename="clipo_brain.json"):
        self.filename = filename
        self.memory = {
            "aliases": {},
            "preferences": {},
            "history_stats": {"success": 0, "failure": 0},
            "custom_shortcuts": {}
        }
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.memory = json.load(f)
            except Exception as e:
                logger.error(f"Error loading memory: {e}")

    def save(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving memory: {e}")

    def add_alias(self, alias, target):
        self.memory["aliases"][alias.lower()] = target
        self.save()

    def record_stat(self, success=True):
        if success:
            self.memory["history_stats"]["success"] += 1
        else:
            self.memory["history_stats"]["failure"] += 1
        self.save()

    def get_summary(self):
        """Returns a string summary for LLM context."""
        summary = "CONOCIMIENTO ADQUIRIDO (Aprendido):\n"
        if not self.memory["aliases"]:
            summary += "- Aún no he aprendido alias personalizados.\n"
        else:
            for alias, target in self.memory["aliases"].items():
                summary += f"- Alias '{alias}' mapea a '{target}'\n"
        return summary

memory_manager = MemoryManager()
