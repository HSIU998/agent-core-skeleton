# 驗證工具：原系統現況 vs 這裡示範的寫法

作品集只能用文字說「我怎麼驗」。這四支讓人自己跑一次，看到它擋下什麼、排出什麼。每一列照實標：原系統現在是怎麼做的、這裡示範的是什麼、測試裡的反例在哪。

| 工具 | 原系統現況 | 這裡示範的 | 測試裡的反例 |
|---|---|---|---|
| `verification/closure_check.py` 閉環檢查 | 紅燈管的是「每一項修改有沒有回寫」：測試副本的提交沒進帳、帳上的提交找不到、問題總表沒標、藍圖沒有這一項的修復狀態；缺「最終目標／量什麼／過關線」那幾欄是黃燈，擋下一批不擋上線；`--apply` 把狀態寫回藍圖與問題總表 | 缺目標欄就紅；結果分五類（passed／observing／partial／failed／untouched）；「程式有在跑」但目標沒量過的，不准標 passed（R4） | `test_counterexample_mechanism_only_check_passes_an_unfinished_ledger`：只看「程式有跑」的舊檢查，對三項沒量目標的修改亮綠 |
| `verification/canary.py` 金絲雀 | 用模型當審查員之前先出資格考（埋好錯的程式），抓不到的不接上線；審查說的每一條，回程式碼逐條核對成「證實／部分證實／它看錯」；最後驗證權不外包給模型 | 埋錯器（六種改法、可重現）＋兩個分數：召回（抓到幾個）和誤報（乾淨的程式被標幾行），兩個都過線才算可信 | `test_counterexample_recall_alone_trusts_the_reviewer_that_flags_everything`：只量召回，「每一行都說有錯」的審查員拿滿分 |
| `verification/sandbox_guard.py` 沙盒守門 | 守門程式包住測試行程：寫正式路徑、連正式服務的埠、從正式路徑啟動行程都擋下並計數；建沙盒時先放金絲雀，全部抓到才開始用；跟正式環境共用的服務要明寫環境變數才放行 | 同一個模式縮成一個 context manager：三種門、計數、金絲雀；沒包到的（刪檔、改名、子行程、直接開 socket）照實寫在檔頭 | `test_counterexample_without_the_guard_the_test_writes_into_production`：沒有守門，同一段測試把檔案寫進正式資料夾，沒人擋、沒人數 |
| `verification/daily_checkup.py` 每日體檢 | 每天固定時間跑一支唯讀腳本：讀執行紀錄、帳本、告警，不叫模型、不寫任何記憶；已知問題登記在清單，修好就拿掉，再犯自動浮回最上面；每一項跟上一次的自己比 | 同樣的分類（新／變嚴重／已知／今天沒出現），用假的英文紀錄示範；唯讀有測試保證 | `test_counterexample_naive_report_buries_the_new_problem`：沒有已知清單、照次數排，十一個慢性問題把唯一的新問題擠到最後一行 |

## 跑起來

```bash
python -m verification.closure_check verification/examples/ledger.json
python -m verification.daily_checkup verification/examples/today.log --known verification/examples/known.json --baseline verification/examples/baseline.json
python -m unittest tests.test_verification -v
```

`closure_check` 的範例帳故意留了兩個常見錯：C-5 機制面過了就標 passed，C-6 連「量什麼」都沒寫。它的輸出：

```
ledger: 6 entries
by result: failed 1, observing 1, passed 4
RED: 4
  [R4] C-5: booked as passed but the goal was never measured (mechanism only)
  [R1] C-6: missing column: measure
  [R1] C-6: missing column: threshold
  [R4] C-6: booked as passed but the goal was never measured (mechanism only)
YELLOW: 0
verdict: not closed, release blocked
```

`daily_checkup` 的範例紀錄裡有三個已知問題、一個新問題、一個變嚴重的、一個今天沒出現的。它的輸出：

```
## look at these (new or worse)
- NEW   error:router  today 1, yesterday 0
- WORSE timeout:vision  today 7, yesterday 2
## known, unchanged
- fallback:embedding  today 3, yesterday 3  (embedding falls back to cpu on cold start)
- skipped:backup  today 1, yesterday 1  (backup skips when the drive is not mounted)
## not seen today (drop from known if it stays away)
- ^error:watchdog  (watchdog restart loop)
```

`canary` 和 `sandbox_guard` 沒有命令列，用法在各自的檔頭和 `tests/test_verification.py`。

## 這四支共同的限制

- 都是骨架：規則少、格式固定、資料是編的。原系統的版本讀的是真的帳本、真的紀錄、真的藍圖。
- `closure_check` 不會去查證據是不是真的；它只保證「沒寫證據的不能標好了」。證據對不對，要人回去看。
- `canary` 的審查員在測試裡是三個假的（完美、全說好、全說壞）。拿真的模型當審查員時，門檻（召回 0.75、誤報 0.1）要照自己的情況調，而且要重複跑幾個種子。
- `sandbox_guard` 只攔經過 `open` 的寫入和明寫的 `check_*`。要擋子行程和網路，要在行程外面包，不是在裡面包。
- `daily_checkup` 的規則只有四條（fallback／error／skipped／timeout）。真的系統要照自己的紀錄格式加。
