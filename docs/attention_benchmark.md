# Attention heatmap benchmark (2026-11-26)

How well do AdLens attention maps match where real people look? Each method's map was scored against human
eye-tracking with the standard saliency metrics (CC, NSS, AUC-Judd, shuffled AUC, SIM, KLD;
`scripts/saliency_metrics.py`). Maps are compared at 256 px width; 95% bootstrap intervals in brackets.

## Methods

| Name | What it is |
|---|---|
| center | A centre Gaussian: the baseline every model must beat |
| spectral | The old AdLens map (spectral residual + centre prior), used by tests before 2026-11-26 |
| model | UNISAL (Droste, Jiao & Noble, ECCV 2020, Apache-2.0), exported to ONNX; used by new tests |
| personas | The AI persona panel (Claude Haiku 5.5, the real test prompt, 10 personas, one point each) |
| blend | 0.75 model + 0.25 personas |

## MIT1003: 200 everyday photos, 15 viewers, 3 s free viewing

| Method | CC | NSS | AUC-J | sAUC |
|---|---|---|---|---|
| center | 0.42 [0.40, 0.44] | 1.20 | 0.81 | 0.51 |
| spectral | 0.38 [0.35, 0.40] | 1.14 | 0.79 | 0.63 |
| personas | 0.49 [0.46, 0.51] | 1.61 | 0.83 | 0.66 |
| **model** | **0.70 [0.67, 0.72]** | **2.38** | **0.90** | **0.77** |
| blend | 0.71 [0.69, 0.72] | 2.39 | 0.90 | 0.77 |

Paired per image: the model beats the old map on 94% of images (CC +0.32); the personas beat the centre blob
(CC +0.07, sAUC on 85% of images); adding personas to the model adds CC +0.01 and nothing on NSS/sAUC.
The UNISAL weights used were not trained on MIT1003.

## UEyes posters: 359 posters and ads, ~10 viewers each (CHI 2023, CC BY 4.0)

| Viewing time | center | spectral | personas | **model** | blend |
|---|---|---|---|---|---|
| first 1 s (CC) | 0.19 | 0.22 | 0.16 | **0.27** | 0.27 |
| first 3 s (CC) | 0.19 | 0.30 | 0.22 | **0.41** | 0.41 |
| 7 s (CC) | 0.27 | 0.39 | 0.28 | **0.51** | 0.52 |
| 3 s (NSS) | 0.35 | 0.65 | 0.46 | **0.87** | 0.87 |

Text-heavy posters are harder for every method (the UEyes paper reports the same for models trained on
natural images). The persona points are close to the centre blob here, and below it for the first second, even
though the prompt asks where the eyes land first.

## What it means

- The trained model is the best map on both datasets, so new tests use it by default (worker snapshot
  `adlens-worker-v2`). The old map was no better than a centre blob on photos.
- The AI personas' own points carry some real signal on photos, little on posters. Present them as "where
  each persona says they look, and why", not as measured gaze.
- Not yet measured: video (no openly licensed ad-video eye-tracking set; DHF1K / DIEM are options), and whether
  the panel's interest scores predict real campaign results (needs past CTR/VTR or A/B outcomes).

## Reproduce

```
git clone --depth 1 https://github.com/rdroste/unisal.git .saliency/unisal
.saliency/venv/bin/python scripts/export_saliency_model.py
.saliency/venv/bin/python scripts/benchmark_manifest.py mit1003 200
.venv/bin/python scripts/benchmark_persona_gaze.py .saliency/data/manifest_mit1003.json .saliency/data/personas_mit1003.json
.saliency/venv/bin/python scripts/saliency_benchmark.py .saliency/data/manifest_mit1003.json .saliency/results/mit1003 --personas .saliency/data/personas_mit1003.json
```

Data sources: MIT1003 (people.csail.mit.edu/tjudd/WherePeopleLook; ALLSTIMULI + ALLFIXATIONMAPS),
UEyes (zenodo.org/records/8010312; poster images and fixation maps only). Kept in `.saliency/`, not in git.
Cost of the persona runs: about $0.65.
