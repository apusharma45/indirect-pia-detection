# Kaggle notebook workflow

`indirect-pia-detection.ipynb` is the only orchestration notebook needed for the base-paper reproduction.

## How the notebook uses the Python implementation

The first code cell clones or updates this GitHub repository at:

```text
/kaggle/working/indirect-pia-detection
```

It then changes the notebook process's working directory to that clone. Every later command therefore executes the version-controlled implementation from GitHub. For example:

```text
Notebook stage: deberta_full
    -> python -m deepspeed.launcher.runner
    -> train_head.py from the cloned repository
    -> generation_dataset.py, sft_trainer.py, and utils.py imported by train_head.py
    -> data/*.json from the cloned repository
```

The notebook does not contain a second implementation of the paper. It selects paths and arguments, launches the authors' Python entry points, captures logs, and converts evaluation logs into structured results.

## Running one stage

1. Open the latest `indirect-pia-detection.ipynb` from GitHub in Kaggle.
2. Enable Internet and a GPU accelerator.
3. In the **Stage control** cell, set `ACTIVE_STAGE` to exactly one stage.
4. If the stage consumes a checkpoint from an earlier Kaggle session, attach that saved Kaggle output and update the corresponding checkpoint path in the same cell.
5. Run all cells.
6. Inspect the final review cell.
7. Save a Kaggle version with notebook outputs. For a training stage, also enable saving notebook output files so the checkpoint can be attached to the next session.
8. Export/update the same notebook on GitHub, then pull the repository locally for diagnosis.

Only one expensive stage runs per execution. All other stages print that they were skipped.

## Intended stage order

```text
audit
deberta_smoke
deberta_full
deberta_eval_squad
deberta_eval_trivia
generative_train
generative_eval_squad
generative_eval_trivia
extraction_train
removal_segmentation_squad / removal_segmentation_trivia
removal_extraction_squad / removal_extraction_trivia
final_asr_segmentation_squad / final_asr_segmentation_trivia
final_asr_extraction_squad / final_asr_extraction_trivia
```

Do not skip directly to later stages merely because their cells exist. A stage should be activated only after the previous required checkpoint or result has been validated.

## Checkpoints versus GitHub results

- Small logs, JSON, CSV, and notebook outputs are suitable for GitHub.
- Model checkpoints under `artifacts/models/` are intentionally ignored by Git.
- Preserve checkpoints using Kaggle notebook output/model storage or an explicitly configured Hugging Face repository.
- Never put Hugging Face or GitHub tokens in a notebook cell. Use Kaggle Secrets.
