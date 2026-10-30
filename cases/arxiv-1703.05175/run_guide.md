# Run Guide — Prototypical Networks on Omniglot

Paper: **Prototypical Networks for Few-shot Learning** (Snell, Swersky, Zemel), arXiv:1703.05175v2 — [abs page](https://arxiv.org/abs/1703.05175) | [PDF](https://arxiv.org/pdf/1703.05175)
Official code: [jakesnell/prototypical-networks](https://github.com/jakesnell/prototypical-networks) (MIT)
Prototype scope: **Omniglot few-shot classification** (Section 3.1). The miniImageNet and CUB experiments are out of scope for this guide (see gaps in [paperlab_design.md](paperlab_design.md)).

How to read this guide: every step is marked **[paper, p.N]** when the methods text supports it (quoted), **[repo]** when it comes from the official code repository, or **[inferred]** when reasoned by PaperLab and needing your confirmation. Page numbers refer to the arXiv v2 PDF.

---

## Before you start

**Step 0. Confirm the environment decision (human).**
The paper states no software or hardware. The repo says it was "tested on Ubuntu 16.04 with Python 3.6 and PyTorch 0.4" ([repo README](https://github.com/jakesnell/prototypical-networks)). PyTorch 0.4 GPU wheels predate modern drivers; the verified CPU-only wheel is [here](https://download.pytorch.org/whl/cpu/torch-0.4.0-cp36-cp36m-linux_x86_64.whl). You must choose: (a) CPU-only on pinned 2018-era versions, or (b) adapt the code to modern PyTorch. PaperLab will not make that call for you.

## Part 1 — Set up the environment

**Step 1. Get the code.**
```bash
git clone https://github.com/jakesnell/prototypical-networks.git
cd prototypical-networks
```
**[repo]** — this is the authors' official implementation of the method described in Section 2 of the paper.

**Step 2. Create a Python 3.6 environment and install dependencies.**
```bash
# Option A (pinned, matches repo's tested setup):
conda create -n protonets python=3.6
conda activate protonets
pip install https://download.pytorch.org/whl/cpu/torch-0.4.0-cp36-cp36m-linux_x86_64.whl
pip install torchvision  # 0.2.x, the PyTorch-0.4-era release
pip install git+https://github.com/pytorch/tnt.git@master   # torchnet
pip install tqdm numpy
```
**[repo]** — README: "Install PyTorch and torchvision", "Install torchnet", "Install the protonets package by running `python setup.py install`". Exact versions beyond Python 3.6 / PyTorch 0.4 are **not pinned** by the repo — treat Option A as **[inferred]** and record what you actually installed (`pip freeze > requirements-lock.txt`) so your run record shows the real environment.

**Step 3. Install the protonets package.**
```bash
python setup.py install
```
**[repo]** — README install instructions.

## Part 2 — Get the data

**Step 4. Download Omniglot.**
```bash
sh download_omniglot.sh
```
**[repo]** — README: "Run `sh download_omniglot.sh`."
Data facts you should verify against the paper:
- The paper describes the dataset as "a dataset of 1623 handwritten characters collected from 50 alphabets. There are 20 examples associated with each character" **[paper, p.5]**.
- The script fetches `images_background.zip` and `images_evaluation.zip` from [brendenlake/omniglot](https://github.com/brendenlake/omniglot) (MIT-licensed dataset; both URLs verified to return HTTP 200).
- Class splits: "We use 1200 characters plus rotations for training (4,800 classes in total) and the remaining classes, including rotations, for test" **[paper, p.5]** — the repo ships these as `data/omniglot/splits/vinyals/`.

## Part 3 — Train

**Step 5. Check that the run configuration matches the paper's method.**
The repo defaults encode the paper's hyperparameters. Before training, confirm each of these against the quotes:

| Setting | Repo default | Paper (p.5, Section 3.1) |
|---|---|---|
| Distance | Euclidean | "We trained prototypical networks using Euclidean distance in the 1-shot and 5-shot scenarios" |
| Training way | `--data.way 60` | "training episodes containing 60 classes" |
| Query points | `--data.query 5` | "and 5 query points per class" |
| Optimizer | `--train.optim_method Adam` | "All of our models were trained via SGD with Adam" |
| Initial LR | `--train.learning_rate 0.001` | "an initial learning rate of 10^-3" |
| LR decay | `--train.decay_every 20` epochs x 100 episodes/epoch = 2000 | "cut the learning rate in half every 2000 episodes" |
| Test way | `--data.test_way 5` | Table 1 reports 5-way; use `--data.test_way 20` for the 20-way results |
| Test episodes | `--data.test_episodes 100` per epoch | paper averages over 1000 test episodes (the eval script generates fresh episodes; confirm count) |

**[paper, p.5 + repo defaults]** — the correspondence above is PaperLab's alignment of repo flags to paper text; verify before running. **The total number of training episodes is not stated in the paper** — the repo default is `--train.epochs 10000` with early stopping (`--train.patience 200`). That is **[inferred]** and needs a human decision.

**Step 6. Run training.**
```bash
python scripts/train/few_shot/run_train.py            # 5-shot scenario (repo default)
python scripts/train/few_shot/run_train.py --data.shot 1 --data.test_shot 1   # 1-shot scenario
python scripts/train/few_shot/run_train.py --data.test_way 20                 # 20-way evaluation
```
**[repo]** — README: "Run `python scripts/train/few_shot/run_train.py`. This will run training and place the results into `results`." The shot/way flags follow from the paper: "it is usually best to train and test with the same 'shot' number" **[paper, p.4, Section 2.6]** and Table 1's four settings.
Add `--data.cuda` if on a GPU **[repo]**.

**Step 7. Re-train in trainval mode.**
```bash
python scripts/train/few_shot/run_trainval.py
```
**[repo]** — README: "Re-run in trainval mode... This will save your model into `results/trainval` by default." (This implements the paper's evaluation discipline of training on training classes and retraining on train+validation classes before testing on novel classes; the paper describes the splits in Section 3.1.)

## Part 4 — Evaluate and compare

**Step 8. Run evaluation.**
```bash
python scripts/predict/few_shot/run_eval.py --model.model_path results/trainval/best_model.pt
```
**[repo]** — README evaluate instructions.

**Step 9. Compare your numbers against the paper (human judgment).**
- The paper's evaluation protocol: "We computed classification accuracy for our models averaged over 1000 randomly generated episodes from the test set" **[paper, p.5]**.
- Compare against Table 1 (p.5): 5-way 1-shot 98.8%, 5-way 5-shot 99.7%, 20-way 1-shot 96.0%, 20-way 5-shot 98.9% — full data in `expected_results.json`.
- Episodes are **randomly generated** and no random seed is stated in the paper or repo, so your numbers will differ slightly. PaperLab only reports your measured values and the paper's values side by side. Whether the outcome counts as a successful reproduction is the **professor's verdict**, recorded in the run record.
