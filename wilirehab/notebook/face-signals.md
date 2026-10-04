# Face signals: pain expression, heart rate, HRV

[AI-assisted] 2026-10-04. Written from paper abstracts and the open-access pages that could be read in a browser, not from PDFs. Under rule R4 none of these is citable until someone opens the PDF and copies a line and a page. Status stays `lead`.

Code: `host/wilirehab/pspi.py`, `face_strain.py`, `hrv.py`, `rppg.py`, `discomfort.py`. Nothing here trains a model or loads a weight file.

## What the code reports

Three separate readings, not one blended score. The weights that would blend them have never been fitted to anyone, so inventing them would be a number with nothing behind it.

| Reading | Meaning | Backed by | Weakness |
|---|---|---|---|
| `pspi` (0 to 16), `strain` (same as 0 to 1) | Facial pain expression | Prkachin and Solomon 2008; Lucey et al. 2011 | A lower bound here (see below) |
| `bpm`, `hr_quality` | Pulse rate | Wang et al. 2017 (POS); de Haan and Jeanne 2013 (CHROM) | Heat, caffeine, anxiety and motion also move it |
| `rmssd_ratio`, `lf_hf_ratio` | HRV now against this person's rest window | Koenig et al. 2014; Shaffer and Ginsberg 2017 | Mixed evidence; noisy from a webcam |

## 1. Facial expression: PSPI

```
PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43
```

AU4 brow lowerer, AU6 cheek raiser, AU7 lid tightener, AU9 nose wrinkler, AU10 upper lip raiser: each 0 to 5. AU43 eye closure: 0 or 1. So the scale is **0 to 16**, a 16-point scale (a note passed to us said 0 to 15; the papers say 16).

- Prkachin KM, Solomon PE. The structure, reliability and validity of pain expression: evidence from patients with shoulder pain. *Pain* 2008;139:267-274. 129 people with shoulder pain; the index showed test-retest reliability and concurrent validity with self-reported pain. Status: lead.
- Lucey P, Cohn JF, Prkachin KM, Solomon PE, Matthews I. Painful data: the UNBC-McMaster shoulder pain expression archive database. *IEEE FG* 2011:57-64. Gives the frame-by-frame form and worked examples (two of them are test cases in `tests/test_pspi.py`). Status: lead.

**What this repo can and cannot supply.** PSPI needs FACS-coded intensities. We estimate four of the six units from landmark distances: AU4, AU7, AU10, AU43. AU6 and AU9 are not implemented and are fixed at 0. Because the formula takes the larger of each pair, the result can only under-read; it is a lower bound. The geometric scales (`AU4_FULL` and friends) are placeholders chosen by eye, not fitted to coded video, and the landmark indices were checked only on synthetic points. A trained AU detector would replace `estimate_aus` and keep `pspi()` unchanged. The next section says why these four.

### Why these action units (and not the others)

Two separate decisions. The first has a published basis; the second is ours.

**Decision 1: PSPI uses AU4, AU6/7, AU9/10 and AU43.** Prkachin (1992) found that brow lowering (AU4), orbital tightening (AU6 and AU7), levator contraction (AU9 and AU10) and eye closure (AU43) carried the bulk of the information about pain, and Prkachin and Solomon (2008) found these four "core" actions accounted for most of the variance in pain expression, with brow lowering, orbit tightening, levator contraction and eye closing forming one unitary action. The sum of their intensities is PSPI. Sources as quoted in Lucey et al. 2011 and in Lucey, Cohn et al., *Automatically detecting pain using facial actions* (PMC3296481): Prkachin KM, *Pain* 1992;51:297-306; Prkachin and Solomon, *Pain* 2008;139:267-274. Status: lead.

**Decision 2: we implement AU4, AU7, AU10 and AU43 from landmarks, and skip AU6 and AU9.** This is a build choice, not a finding.

| Unit | What the face does | Landmark distance we use | Why this one was implemented |
|---|---|---|---|
| AU4 brow lowerer | Brow moves down toward the eye | Brow point to the upper-lid point beneath it | A brow-to-eye gap is a direct distance between two landmarks the mesh provides |
| AU7 lid tightener | Eye opening narrows | Eye-aspect ratio (lid gap over eye width) | Same landmarks as AU43; one measurement gives two units, so it was the cheapest to add |
| AU43 eye closure | Eye closed | Eye opening below 25% of the person's own rest value | The same eye-aspect ratio, thresholded; the unit is binary in PSPI, so a threshold matches its definition |
| AU10 upper lip raiser | Upper lip lifts toward the nose | Under-nose point to upper-lip point | A single distance between two mesh landmarks |
| AU6 cheek raiser | Cheek lifts toward the eye | not implemented | Needs cheek-to-eye distances and a stable cheek reference point; not done yet |
| AU9 nose wrinkler | Nose bridge wrinkles | not implemented | Mostly skin texture and small shifts; not done yet |

Honest limits on decision 2:

- It was made for how easy each distance is to compute, not because a paper shows these four distances track the coded units. Nobody has validated our proxies, and the constants are placeholders.
- It is **not** established that AU6 and AU9 cannot be read from landmarks. Meawad F, Yang S-Y, Loy FL, *Automatic detection of pain from spontaneous facial expressions* (University of Glasgow eprint 151491; venue and year not confirmed), adapted PSPI by replacing every unit, AU6 and AU9 included, with a distance measurement (cheek-eye, cheek-nose and similar for AU6, nose and lip distances for AU9 and AU10), and counted activated features instead of summing intensities. So distance features for AU6 and AU9 do exist in the literature; we have not built them. Status: lead.
- The strongest toolkit we saw does not rely on geometry alone. OpenFace estimates AU intensity from an appearance feature (histograms of oriented gradients on an aligned face) together with landmark shape features (Baltrusaitis et al., *OpenFace: an open source facial behavior analysis toolkit*, WACV 2016; *OpenFace 2.0: Facial Behavior Analysis Toolkit*). It recognises AUs 1, 2, 4, 5, 6, 7, 9, 10, 12, 14, 15, 17, 20, 23, 25, 26, 28 and 45, and it was trained on a set that includes the UNBC-McMaster pain archive. Status: lead.
- OpenFace reports **AU45 (blink)**, not AU43 (eye closure). If it replaces `estimate_aus`, AU43 needs a stated mapping, such as AU45 held above a threshold for several frames, and that mapping is our assumption.
- Head pose is a confound for any image-plane distance. OpenFace estimates head pose alongside the landmarks. We do not: tilting or turning the head changes our distances without any expression change. The first live run on 2026-10-04 showed AU4 near 2 while the rest face may simply have moved.

**Decision 3: the rest baseline.** We subtract each person's own neutral face instead of using fixed thresholds. OpenFace does the same kind of thing: it subtracts the median of the features over the video, and removes a low percentile of each person's AU predictions, because predictors "tend to sometimes under- or over-estimate AU values for a particular person" (Baltrusaitis et al., OpenFace 2.0 and WACV 2016). Our version is simpler (a median over the first `--rest-s` seconds) and the 8 to 10 s default is short; the comparable tool calibrates over a whole recording. Status: lead.

Frequency in the UNBC archive (Lucey et al.): of 48,398 coded frames, 83.6% scored 0 and about 0.5% scored 9 or more. `adapt.py`'s default `strain_ease` of 0.6 means PSPI 9.6, which would almost never fire, so `discomfort.STRAIN_EASE_SUGGESTED` is PSPI 3 (3/16). That value is a placeholder, not a clinical cut-off.

## 2. Heart rate and HRV

Beats are timed on the pulse waveform, cleaned, then summarised as RMSSD and LF/HF (bands LF 0.04 to 0.15 Hz, HF 0.15 to 0.40 Hz).

What the evidence supports:

- **Direction in pain.** Koenig J, Jarczok MN, Ellis RJ, Hillecke TK, Thayer JF. Heart rate variability and experimentally induced pain in healthy adults: a systematic review. *Eur J Pain* 2014;18:301-314. 20 studies; best-evidence synthesis is a rise in baroreflex-related LF measures and a fall in vagal HF and RMSSD during acute pain. Status: lead.
- **It is not consistent.** "Heart Rate Variability and Pain: A Systematic Review", *Brain Sciences* 2022;12(2):153, 71 studies. The response depends on the stimulus, breathing, sex, age and attention, and several cold-pain studies saw RMSSD rise. Status: lead.
- **LF/HF is not a fight-or-flight meter.** Koenig et al. say LF reflects baroreflex activity rather than sympathetic activity, and Shaffer F, Ginsberg JP, *An overview of heart rate variability metrics and norms*, *Front Public Health* 2017;5:258, say that at rest LF reflects baroreflex activity and not cardiac sympathetic innervation. So a spike in LF/HF is not evidence of "sympathetic activation" by itself. Status: lead.
- **Window length.** Shaffer and Ginsberg: RMSSD about 60 s (30 s proposed), LF at least 2 min and 2.5 min of clean data. `hrv.py` returns None below 60 s and 150 s respectively rather than printing a number.
- **Camera accuracy.** Tohma A et al., *Evaluation of Remote Photoplethysmography Measurement Conditions toward Telemedicine Applications*, 2021: at 30 fps and 500 lux from the front, LF, HF and LF/HF correlated about 0.9 with ECG, and accuracy dropped sharply with head motion. "Robust Heart Rate Variability Measurement from Facial Videos" (PMC10376629) reports a best RMSSD error near 10 ms on UBFC-rPPG, against a resting range of 19 to 75 ms. A game with a moving head is the bad case. Status: lead.

So the HRV numbers are supporting signals. They are never combined into the facial score and never used alone to decide something is painful.

## 3. Pulse-rate methods

- Wang W, den Brinker AC, Stuijk S, de Haan G. Algorithmic principles of remote PPG. *IEEE TBME* 2017. POS, the default. Status: lead.
- de Haan G, Jeanne V. Robust pulse rate from chrominance-based rPPG. *IEEE TBME* 2013. CHROM, `method="chrom"`. Status: lead.

Both are closed-form; neither is trained.

## Datasets

We train nothing, so no training set is needed.

- PSPI and the AU scales come from the UNBC-McMaster archive's coding, but the archive itself is licensed and is not in this repo.
- Evaluation of the pulse code, if wanted later, would use public lab video (PURE, UBFC-rPPG). Those are for offline checking and should not be committed here.
- The check that matters for our paper is a table from the author: oximeter bpm beside camera bpm, the quality flag, the lighting, and whether the facial score rose when a movement actually hurt.

## What would need a model

Only one thing: a facial action-unit detector, if you want AU6 and AU9 and calibrated intensities instead of the lower-bound geometry. If you have one you trust, send its name and how it is installed; `estimate_aus` is the single function it would replace.

## Changelog
| Date | Change |
|---|---|
| 2026-10-04 | Page created: PSPI, HRV, and the pulse methods. PDFs not opened. |
