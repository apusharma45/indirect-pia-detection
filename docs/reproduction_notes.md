# Reproduction notes

## Experiment: Kaggle environment and data audit

### Paper / author environment

- Python requested by README: 3.9
- PyTorch pinned by requirements: 2.3.1+cu121
- Transformers: 4.47.1
- DeepSpeed: 0.16.2
- Reported paper hardware: one NVIDIA H100 96 GB
- Precision in the DeBERTa command: bf16

### Observed Kaggle environment

- Python: 3.13.15
- PyTorch: 2.11.0+cu128
- Transformers: 5.16.1
- DeepSpeed: not installed
- GPU: two Tesla T4 GPUs with 14.56 GiB each
- CUDA was available; the PyTorch runtime probe reported bf16 support

### Result

Environment capture and all five dataset validations succeeded. No model was loaded or trained. See `results/environment.txt` and `results/data_summary.json`.

## Experiment: deberta_squad_smoke (prepared, not yet run)

### Paper setting retained

- model: `microsoft/deberta-v3-base`
- training entry point: unmodified `train_head.py`
- DeepSpeed: 0.16.2
- Transformers: 4.47.1
- learning rate: 1e-5
- epochs: 1
- train batch size: 4
- micro batch size: 4
- injection rate: 0.6
- head/tail conditional rates: 0.25/0.25
- ZeRO stage: 1
- Adam offload: enabled
- seed: 42
- precision: bf16 on the first attempt
- GPU count used: one, matching the paper's single-GPU topology

### Reproduction setting

- Kaggle host Python, PyTorch, and CUDA are retained.
- Only the minimum user-space packages needed by the original path are pinned in `configs/kaggle-smoke-requirements.txt`.
- The smoke subset contains the first 16 SQuAD contexts and first 64 Alpaca instructions.
- Expected optimizer steps: 4.
- Checkpoint output is ignored by Git and only small evidence files under `results/deberta_smoke/` are returned.

### Reason for deviation

The full author `requirements.txt` contains a machine-local `mpi4py` URL, separately pinned CUDA wheels, and a PyTorch build that would replace Kaggle's working CUDA stack. The small subset is required to validate compatibility before spending GPU time on the full 18,891-context run.

### Expected impact

The subset makes the smoke loss and class mix non-comparable with the paper. Retaining Kaggle's newer PyTorch may expose incompatibilities with DeepSpeed 0.16.2. Tesla T4 bf16 behavior must be established by the actual training attempt rather than inferred from the runtime probe.

### Observed impact

Pending Kaggle execution. This section must be updated from `results/deberta_smoke/metrics.json`, `training_log.txt`, and `error.txt` if present.
