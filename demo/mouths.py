"""Replaceable generation layer. A mouth only turns prepared context into a line."""
import json
import os
import urllib.request


class EchoMouth:
    """Deterministic stand-in for a model: says which memories it was handed."""
    name = "echo"

    def speak(self, persona_name: str, memories: list[str], user_text: str) -> str:
        if not memories:
            return f"{persona_name}: I don't remember anything about that."
        return f"{persona_name}: I remember - " + " / ".join(memories)


class TerseMouth(EchoMouth):
    """A second 'model' with a different voice, to show the swap keeps the state."""
    name = "terse"

    def speak(self, persona_name, memories, user_text):
        return f"[{persona_name}] " + (memories[0] if memories else "no memory")


class OllamaMouth:
    name = "ollama"

    def __init__(self, model: str | None = None, url: str | None = None):
        self.model = model or os.environ["OLLAMA_MODEL"]
        self.url = url or os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")

    def speak(self, persona_name, memories, user_text):
        recalled = "\n".join(f"- {m}" for m in memories) or "- (nothing came to mind)"
        body = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": f"You are {persona_name}. Things you recalled before answering:\n{recalled}"},
                {"role": "user", "content": user_text},
            ],
        }
        req = urllib.request.Request(self.url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["message"]["content"]


def from_env():
    return OllamaMouth() if os.environ.get("DEMO_MOUTH") == "ollama" else EchoMouth()
