# Reproduction status

## Completed: environment and data validation

The first Kaggle run completed successfully. It was an engineering validation run, not a scientific experiment, and produced no detection metrics.

- Python: 3.13.15
- GPU: 2 × Tesla T4, 14.56 GiB each
- CUDA available: yes
- PyTorch: 2.11.0+cu128
- Transformers before setup: 5.16.1
- DeepSpeed before setup: not installed
- Runtime bf16 probe: reported supported
- Dataset validation: 5 valid JSON files, 58,848 total records, no malformed records
- Dataset hashes: unchanged from the local audit

The environment report was recovered verbatim from the executed notebook output and saved as `results/environment.txt` because the first Kaggle commit embedded outputs in the notebook but did not commit the generated result files.

## Single next experiment

Run `deberta_squad_smoke` on one T4 through the authors' unmodified `train_head.py` and DeepSpeed path, using 16 SQuAD contexts and 64 Alpaca instructions. This checks dependency installation, model/tokenizer download, dataset construction, forward/backward loss, four expected optimizer steps, and model saving.

The smoke result is not scientifically comparable with the paper. Full training must wait until the smoke result has been inspected.
