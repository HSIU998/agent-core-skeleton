# ADR-002 要保證的事放進程式，不寫在提示詞裡拜託模型

**背景**：原系統把「先查記憶」寫在提示詞裡，交給模型自己決定要不要呼叫查詢工具。量了 9 天、783 輪，雲端模型回傳工具呼叫 0 次。

**決定**：判斷在程式、執行也在程式。開口前由程式決定要不要查、查好放進上下文，模型只拿結果（`demo/turn.py`、`retrieval/router.py`）。

**代價**：程式要自己判斷「這一輪要不要查」。判斷交給模型分類時，模型壞掉就要有退路——原系統在這裡失敗時一律回「不用查」，等於把查記憶靜默關掉。`retrieval/router.py` 失敗時改用規則判斷。

**反例**：`tests/test_retrieval.py::test_counterexample_all_false_on_failure_skips_memory`。
