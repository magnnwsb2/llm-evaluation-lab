# Evidence ledger — Stage 027 (reviewed 2026-11-08)

**Scope:** five **manually dispatched** GitHub Actions run artifacts read as ZIPs and independently cross-checked against GitHub's run metadata and artifact SHA-256. This is a **sanitized inventory**, not a substitute for the raw evidence. No response bodies, prompt text, expected answer strings, Cloudflare credentials, account identifiers, token counts or spending amounts are reproduced here.

All experiment data are **synthetic**, not real customer records. An `error` means a case could not be evaluated; it is **not** a wrong model answer. The reported latencies are **client-observed HTTP round trips**, not model token-generation durations.

| Workflow run | Experiment / model | Commit SHA | Passed / failed / errors | Observed per-case latency (ms) | GitHub artifact ID |
|---|---|---|---:|---|---:|
| [42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221) | `smoke-001` / Llama 3.1 8B FP8 | `61fd68ae0d51d646e33db13c8187f3b6351e8220` | 3 / 0 / 0 | 492, 1133, 523 | 13626453779 |
| [42511351245](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42511351245) | `advanced-001` / Llama 3.1 8B FP8 | `6f90b6a2e9cea68e9d6f4087cb2662ba562e734b` | 2 / 1 / 0 | 2760, 670, 717 | 13629072925 |
| [42519170795](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42519170795) | `robustness-001` / Llama 3.1 8B FP8 | `f7f98c3082f92508ef06a1cbc02b7a60c6acfe90` | 1 / 2 / 0 | 5406, 443, 2108 | 13632451760 |
| [42527009736](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527009736) | `smoke-002` / Gemma 4 26B A4B | `169486a67ee65b678051700f14a7623d7bed1632` | 0 / 0 / 3 | **9536, null, null** | 13635392822 |
| [42527365653](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527365653) | `smoke-002` / Gemma 4 26B A4B | `2d1de4086836542a92ae965515232a0411a5a073` | 3 / 0 / 0 | 1291, 596, 410 | 13635721969 |

**Precisely observed failure:** the first Gemma run (#42527009736) attempted one request, returned `invalid_response` after 9,536 ms and then **skipped both remaining requests** (null durations). The error cause cannot be diagnosed definitively because the raw provider response was not logged or preserved after rejection. A later run, after the Stage 026.1 `enable_thinking=false` change, succeeded on all three small cases. Temporal correlation is not proof of causation.

**Successful Gemma smoke:** the three strict outcomes were `greeting-001` exact pass (1291 ms), `keyword-001` contains pass (596 ms) and `digits-001` regex pass (410 ms); observed mean HTTP latency **765.67 ms**. The previously reviewed Llama smoke used exactly the same questions, but different model/code/time/network conditions. These observations **are not** controlled performance benchmarking or proof of general model quality.

## Provider-reported artifact ZIP SHA-256

Each digest below was also reproduced by hashing the downloaded ZIP; it is **not** a signature of Cloudflare's API response or an attestation that a model ran.

| GitHub run | GitHub artifact ZIP SHA-256 |
|---|---|
| 42504084221 | `9af4dc1ec2fa8d8fa79a8cc5837088a10413915db71da035f2f46492b88e25bd` |
| 42511351245 | `d53e422b0805c758dc761c61ae1b71f1a2a481cf53b792ed09ca196b4f303a3b` |
| 42519170795 | `01c1f896509b89ecff64346b4e29956f550bd6a6700975f0cc033aa3101ec7b3` |
| 42527009736 | `f556147b520ba22afbef0f50b6f9fa58384a2fecd99ca2c43f28c48fd6ae1cf8` |
| 42527365653 | `17ef418c22ce1009255735843d5a56b05fef66e1627521d288251eaa0214cc5a` |

**Retention and access:** GitHub Actions artifacts here were configured for **7-day retention**, and the copies reviewed were scheduled to expire on **2026-11-15 UTC**. A link or hash may no longer resolve later. Public-repository Actions artifacts may be available to others via GitHub: the original `results.json` includes **full synthetic model responses** even though the GitHub Pages dashboard and logs intentionally exclude them. **Never submit real customer information, credentials or other private data** through these experiments. No permanent archival copy of raw responses is made by Stage 027.

**Public dashboard publication boundary:** only the **three separately reviewed Llama `*-001` snapshots** are in `dashboard/approved/` and GitHub Pages. The failed and successful Gemma `smoke-002` runs are **documented here, not published as new Pages result cards**. Adding a Gemma public snapshot would require independent approval, a strictly sanitized allowlisted record, tests, and its own reviewed publication change.

**Cost boundary:** the user previously showed Workers Free active and a screenshot with 16.25 of 10,000 daily Neurons used (at that moment, attributed to Llama); **there is no here-verified post-Gemma billing or balance statement**. Zero paid services were provisioned in this repo; that is different from a guarantee that cloud metering can never change.
