# Final shipment qualification and study closeout

Llama 3.2 3B Instruct Q4_K_M made 5/18 correct decisions, including 4/18 with sufficient citations. It missed all six required stops, released unsafely three times, and withheld all six eligible releases. The most common response was abstention (15/18). The frozen gate requires 18/18 supported correct.

The [pre-inference decision](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/105#issuecomment-7206055150) capped the remaining work at one configuration. Qualification failed and the conditional held-out comparison was skipped. Shipment testing is closed. The #138 improvement from 28/48 to 48/48 remains a deterministic result on constructed histories. The effect on model decisions is unmeasured.

## Evidence and verification

[Raw prompts, outputs, and per-trial scores](shipment-llama-final-replay.json), SHA-256 after LF normalization: b6bfdf31da973ee70aaba3e731dca960fafc55fa807ed40f67c962dda6011124. An independent recount decoded the raw action labels using the displayed legends, reconstructed current rows from the prompts and checked citation sufficiency on every trial.

[Runner](../../scripts/evaluate_shipment_llama_final.py) uses the #140 fixtures and the #139 scorer and response grammar. It substitutes native Llama user/assistant delimiters, starts a new CPU process for each trial, and verifies model, CLI and source hashes. The weights correspond to the Ollama llama3.2 model layer whose digest is pinned in the runner. Use the llama.cpp b6500 win-cpu-x64 release ZIP (SHA-256 73e00267e852e666a6fce2c3fb7a2603dd1934a37259f3f45c2c1b6983fa605a). Archived inference used Python 3.11 on Windows with an empty shim for an unused Unix resource import in a transitive dependency.

To replay on Windows from an LF checkout, set PYTHONPATH to src;scripts and run the following with the paths to the two pinned artifacts:

```powershell
python -c "import runpy,sys,types;sys.modules['resource']=types.ModuleType('resource');runpy.run_module('evaluate_shipment_llama_final',run_name='__main__')" --model <model-path> --cli <llama-cli-path>
```
