# Repository audit: official indirect-PIA implementation

Audit date: 2026-10-07  
Upstream: <https://github.com/LukeChen-go/indirect-pia-detection>  
Scope: the official source and supplied JSON files currently copied into this repository.

## Baseline-integrity policy

The root-level paper implementation is the baseline and must remain unchanged during the initial reproduction. In particular, do not edit `chatbot.py`, `generation_dataset.py`, `instruction_attack_defense_tools.py`, `sft_trainer.py`, `train*.py`, `run_*.py`, `utils.py`, `requirements.txt`, or the files under `data/` merely to make them easier to run. Reproduction helpers belong under `scripts/`, `docs/`, and `results/`. Any later compatibility patch must be isolated and recorded as a deviation before it is used.

The imported upstream tree has no upstream `.git` metadata, so its original commit SHA cannot be recovered locally. The first commit made in this repository after import will pin the exact files used here.

## Files and entry points

| File | Purpose | Inputs | Outputs / side effects | Models |
|---|---|---|---|---|
| `README.md` | Upstream setup and example commands. | None. | Human instructions only. | DeBERTa-v3-base, Llama 3.2 1B/3B, Llama 3 8B. |
| `requirements.txt` | Full pinned author environment. | `pip`. | Installs training, inference, API, and CUDA dependencies. | N/A. |
| `train_head.py` | **Discriminative detector training entry point.** Creates `HeadDataset`, a sequence-classification model, DeepSpeed optimizer/scheduler, and `HeadTrainer`. | Alpaca instruction JSON, clean-context JSON, model ID, DeepSpeed CLI settings. | Saved Hugging Face model/tokenizer and a log containing the parsed arguments. | `AutoModelForSequenceClassification`; README target is `microsoft/deberta-v3-base`. |
| `train_classification.py` | Generative yes/no detector training entry point. | Same training sources plus an injection-QA evaluation JSON. | Saved causal LM/tokenizer, progress output, evaluation values printed by its trainer. | README target is gated `meta-llama/Llama-3.2-1B-Instruct`. |
| `train.py` | Injected-instruction extraction training entry point. | Alpaca instructions, clean contexts, injection-QA evaluation data. | Saved causal LM/tokenizer and trainer logs. | README target is gated `meta-llama/Llama-3.2-3B-Instruct`. |
| `generation_dataset.py` | Runtime dataset construction, injection placement, prompts, tokenization, and collation. | Source JSON files and tokenizer. | In-memory tensors and labels; it does not persist the randomly constructed training set. | Tokenizer-dependent. |
| `sft_trainer.py` | Training loops and losses for extraction, generative classification, and discriminative classification. | DeepSpeed-wrapped model, loaders, optimizer, scheduler. | Progress bars/evaluation prints; optimization steps. | Model-agnostic trainer classes. |
| `utils.py` | JSON/logging helpers and the custom DeepSpeed strategy, optimizer, dataloaders, save/load behavior, and tokenizer setup. | Parsed CLI arguments and models. | Initializes distributed execution, creates DeepSpeed engines, saves checkpoints/models. | DeepSpeed, PEFT, Transformers. |
| `run_detection.py` | **Detection evaluation entry point.** Applies each attack/position and calls the selected detector. | Trained detector, injection-QA JSON, attack names, sides. | Text log with `ACC` and mean cost for each attack/side. | Discriminative detector, generative detector, Guard, or GPT classifier. |
| `run_purify.py` | Removal evaluation entry point. | Detector/extractor, injection-QA JSON, attacks, positions, purification method. | Text log with fraction of injected strings removed and mean cost. | Discriminative/generative detector and optional extraction model. |
| `run_evaluation_instruction.py` | End-to-end attack/defense and ASR evaluation. | Target LLM, optional filter/extractor, data, attack, defense, side. | Text log with ASR, removal value, and cost. | Hugging Face or GPT target LLM plus optional defense models. |
| `instruction_attack_defense_tools.py` | Attack templates, start/middle/end insertion, prompt assembly, and non-model defenses. | One benchmark record and runtime options. | Modified in-memory copies and formatted model inputs. | None directly. |
| `chatbot.py` | Model adapters for target LLMs, generative/discriminative detectors, Guard, GPT, segmentation removal, and extraction removal. | Model IDs/checkpoint paths and text. | Predictions, responses, or purified text. | Transformers models or OpenAI client. |

`train_head.py`, `train_classification.py`, and `train.py` are the training entry points. The three `run_*.py` files are evaluation entry points. The other Python files are imported support modules.

## Supplied data

The read-only inspection in `results/data_summary.json` records hashes, schemas, representative truncated records, and validation details. All five files are valid top-level JSON arrays with no non-object records and no fields missing from their modal schema.

| File | Records | Observed schema | Role |
|---|---:|---|---|
| `crafted_instruction_data_alpaca.json` | 19,157 | `instruction`, `input`, `output` | Pool of injected instructions used during training. |
| `crafted_instruction_data_context_squad.json` | 18,891 | `id`, `title`, `context`, `question`, `answers` | SQuAD clean training contexts. |
| `crafted_instruction_data_context_tri.json` | 19,000 | `context` | TriviaQA clean contexts for the other-domain setting. |
| `crafted_instruction_data_squad_injection_qa.json` | 900 | `instruction`, `input`, `output`, `injection`, `injection_output` | Inj-SQuAD evaluation benchmark. |
| `crafted_instruction_data_tri_injection_qa.json` | 900 | `instruction`, `input`, `output`, `injection`, `injection_output` | Inj-TriviaQA evaluation benchmark. |

There are no persisted binary labels, attack labels, or position labels in these JSON files. Training labels and injection positions are generated at dataset construction time. Evaluation attack types and positions are supplied on the command line and applied in memory.

The README refers to `crafted_instruction_data_davinci.json`, but that file is not supplied. In the current `run_detection.py` and `run_purify.py`, `--injected_instruction_data_path` is parsed but its loading is commented out; each benchmark record already has an `injection` field. We should therefore not manufacture the missing file.

## Minimal DeBERTa data and training path

1. `train_head.py` seeds Python, NumPy, and PyTorch with the CLI seed (default 42).
2. It loads `AutoModelForSequenceClassification` and the tokenizer from `microsoft/deberta-v3-base` when invoked as in the README.
3. `HeadDataset` truncates each clean context to 384 tokenizer tokens, randomly chooses an Alpaca instruction, and injects it with probability `--inject_rate`.
4. `insert_instruction` assigns injected examples to tail, head, or middle according to `tail_rate`, `head_rate`, and the remainder. With the paper command (`inject_rate=0.6`, `head_rate=0.25`, `tail_rate=0.25`), the expected total distribution is 40% clean, 15% head, 30% middle, and 15% tail.
5. Clean examples receive label 0 and injected examples label 1. `HeadTrainer` uses cross-entropy loss.
6. The custom strategy initializes DeepSpeed, a distributed sampler, fused/CPU Adam, scheduler, gradient accumulation, and model saving.

Important: `--eval_data_path` is accepted by `train_head.py` but never used. The discriminative trainer has no validation loader and emits no TPR/FPR/accuracy. A successful training run alone therefore cannot satisfy Phase 2; evaluation must later be run separately with `run_detection.py` and its text output parsed into structured metrics.

For `run_detection.py`, an `ACC` value is the fraction classified as injected. Consequently:

- `attack=none`: `ACC` is the false-positive rate (FPR).
- Any injected attack: `ACC` is the true-positive rate (TPR) for that attack/position.

The script selects the discriminative `DetectionChatbot` only when the model path contains the substring `prompt`. The README checkpoint name does contain `prompt`; changing that name would silently select a different adapter.

## Dependency and Kaggle risks

1. The README targets Python 3.9, while Kaggle images may use a newer Python version.
2. `requirements.txt` is an environment freeze, not a portable minimal requirements file. `mpi4py @ file:///croot/...` points to an author-machine path and cannot be installed as written elsewhere.
3. `torch==2.3.1+cu121` and the separately pinned NVIDIA CUDA wheels can conflict with Kaggle's preinstalled PyTorch/CUDA stack. Installing the entire file may replace a working GPU environment.
4. DeepSpeed 0.16.2 may need compilation support compatible with Kaggle's installed PyTorch, CUDA toolkit, and Python. `FusedAdam` is used unless `--adam_offload` selects `DeepSpeedCPUAdam`.
5. The README enables bf16. This must be verified on the assigned Kaggle GPU; it cannot be assumed from CUDA availability alone.
6. `utils.py` always configures parameter offload to CPU for training and optionally optimizer offload. This affects memory and speed and is part of the current baseline behavior.
7. Training initializes a distributed backend even for one GPU. Launching `train_head.py` directly with plain `python` is not equivalent to the documented DeepSpeed path.
8. Model downloads require Kaggle internet access or a pre-attached model dataset. DeBERTa is public; the Llama models used later are gated and require `HF_TOKEN` plus accepted licenses.
9. Log parent directories are not created by the upstream `Logger`; callers must create them before launching.
10. `--max_len` and `--max_samples` are parsed by the training scripts but do not constrain `HeadDataset`. They cannot be used for a genuine smoke subset without a separate wrapper or an explicitly documented compatibility change.
11. The discriminative training loop uses `torch.cuda.current_device()` directly and is not a CPU training path.
12. `run_detection.py` writes only free-form logs; no structured metric file is produced by the baseline.

Additional later-stage risks include a literal placeholder API key in the GPT adapter (it must never be replaced with a committed secret), fixed 40-GiB-per-GPU assumptions in some generative adapters, and brittle model routing based on substrings in checkpoint paths.

## Files to leave unchanged initially

All official root Python files, `requirements.txt`, `README.md`, `LICENSE`, and every file under `data/` should remain byte-for-byte unchanged for the first run. In particular, do not remove DeepSpeed, rewrite the dataset classes, add evaluation to `train_head.py`, or change the attack functions yet.

Our first evidence-producing increment consists only of:

- `scripts/check_environment.py`
- `scripts/inspect_data.py`
- `results/data_summary.json`
- `results/data_summary.md`
- `indirect-pia-detection.ipynb` as a Kaggle orchestrator

## Reproduction execution order

1. Run the environment checker on the assigned Kaggle GPU and commit `results/environment.txt`.
2. Run the data inspector and confirm its hashes/counts match the committed summary.
3. Review Kaggle's Python/PyTorch/CUDA/DeepSpeed/bf16 evidence before installing or changing anything.
4. Prepare and run a DeBERTa smoke test through the original DeepSpeed path. A smoke test is engineering validation, not a scientific result.
5. Run the full one-epoch SQuAD DeBERTa training with the README settings wherever Kaggle supports them; record every unavoidable deviation.
6. Run in-domain detection evaluation, parse FPR/TPR, then run out-of-domain and attack/position evaluations.
7. Compare structured results with the paper before starting the generative detector or either removal method.

No model training was performed during this audit.
