"""One conversational turn. The program recalls before the mouth speaks;
the mouth never decides whether memory gets looked up."""
import time


def run_turn(store, persona: dict, user_text: str, mouth, limit: int = 3) -> dict:
    t0 = time.perf_counter()
    recalled = store.recall(persona["persona_id"], user_text, limit=limit)
    t1 = time.perf_counter()
    reply = mouth.speak(persona["name"], [m["text"] for m in recalled], user_text)
    t2 = time.perf_counter()
    store.log_dialogue(persona["persona_id"], "user", user_text)
    store.log_dialogue(persona["persona_id"], "persona", reply)
    t3 = time.perf_counter()
    return {
        "reply": reply,
        "mouth": mouth.name,
        "recalled_ids": [m["id"] for m in recalled],
        "prefetch_ran": True,
        "timing": {"recall": t1 - t0, "generate": t2 - t1, "write_back": t3 - t2},
    }
