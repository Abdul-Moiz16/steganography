# Reference Review: Relevance and Utility for Our Research

Each of the 15 references in the proposal is reviewed below. For each paper we explain: why it's included, what specific findings or methods are relevant, and how we can use it in our own study.

---

## Audio Steganography Surveys & Techniques

### [1] Djebbar et al. — "Comparative study of digital audio steganography techniques" (EURASIP JASM, 2012)

**Why it's relevant:** This is the most widely cited comparative survey of audio steganography methods. It evaluates LSB, phase coding, echo hiding, and spread spectrum approaches across three axes: hiding capacity, robustness, and imperceptibility.

**What we use from it:** We adopt their capacity–robustness–imperceptibility trade-off framework as the conceptual backbone for comparing embedding methods. Their quantitative comparison of technique properties (Table 2 in their paper) directly informs our choice of LSB and DCT as representative time-domain and frequency-domain methods. We also reference their evaluation criteria when defining our own metrics (PESQ, STOI, SNR).

---

### [2] Kaur & Behal — "Audio steganography techniques — a survey" (IJERA, 2014)

**Why it's relevant:** This replaces the originally mislabeled reference [3] from the first draft (which was Hussain et al.'s *image* steganography survey). Kaur and Behal provide a comprehensive taxonomy of audio steganography that covers spatial, transform, and hybrid methods.

**What we use from it:** Their taxonomy (Section III) provides the classification scheme we reference when explaining why LSB and DCT span the two main embedding paradigms. Their discussion of advanced hybrid methods (Section IV) also motivates our research — none of the surveyed methods consider carrier origin as a variable, reinforcing our novelty argument.

---

## Audio Steganalysis (Traditional + Deep Learning)

### [3] Ghasemzadeh & Kayvanrad — "Comprehensive review of audio steganalysis methods" (IET Signal Processing, 2018)

**Why it's relevant:** The most thorough review of audio steganalysis specifically (as opposed to general steganography surveys). Covers both feature-extraction pipelines (MFCCs, spectral flatness, Markov features) and classification approaches (SVM, ensemble methods).

**What we use from it:** Their categorization of steganalysis features (Table 1) informs our understanding of what statistical properties detectors exploit — which is central to our hypothesis that ML-generated audio's different statistical profile will affect detectability. Their review of detection accuracy across different embedding methods also provides baseline performance expectations for Conditions A and B.

---

### [4] Chen, Luo & Li — "Audio steganalysis with convolutional neural network" (ACM IH&MMSec, 2017)

**Why it's relevant:** Seminal paper introducing CNN-based audio steganalysis. They train a CNN directly on raw audio waveforms to detect ±1 LSB embedding without hand-crafted features.

**What we use from it:** We adopt their CNN architecture as our **baseline classifier** (Architecture 1 in Section 4.4). Their architecture design — 5 convolutional layers with batch normalization on 16,384-sample segments — is directly replicable. Their reported accuracy (~95% on clean LSB at high payload) gives us performance benchmarks to compare against. Crucially, their model was only tested on real audio, so our cross-domain experiments (Conditions C and D) directly extend their work.

---

### [5] Zhang, Yi & Zhao — "Improving audio steganalysis using deep residual networks" (IWDW 2019, Springer 2020)

**Why it's relevant:** Demonstrates that ResNet architectures outperform standard CNNs for audio steganalysis by learning residual maps that amplify subtle embedding artifacts.

**What we use from it:** Their residual learning approach provides theoretical motivation for our Spec-ResNet classifier choice — residual connections help detect the weak signals that steganographic embedding creates. Their finding that deeper networks improve detection at low payload rates is directly relevant to H2 (payload divergence), since we need classifiers sensitive enough to detect subtle differences between carrier types at low embedding rates.

---

### [6] Ren et al. — "Spec-ResNet: A general audio steganalysis scheme based on deep residual network of spectrogram" (arXiv, 2019)

**Why it's relevant:** Proposes our **primary classifier architecture** — a ResNet that operates on spectrogram representations rather than raw waveforms, making it agnostic to the specific embedding domain.

**What we use from it:** We adopt Spec-ResNet as Architecture 2 (Section 4.4) because: (a) it handles both LSB and DCT embedding (essential for RQ2), (b) spectrogram features capture frequency-domain properties that differ between real and ML-generated audio, and (c) their preprocessing pipeline (STFT → log mel-spectrogram → ResNet) is well-documented and reproducible. Their reported detection rates across multiple embedding methods provide the most directly comparable baselines for our study.

---

### [7] Peng, Liao & Tang — "Audio steganalysis using multi-scale feature fusion-based attention neural network" (IET Communications, 2025)

**Why it's relevant:** Represents the current state-of-the-art in audio steganalysis (94.55% accuracy), using multi-scale feature extraction with attention mechanisms.

**What we use from it:** We cite this as evidence that the steganalysis field continues to advance, and that our classifiers (CNN baseline + Spec-ResNet) represent established but not bleeding-edge approaches — appropriate for a controlled comparison study. Their attention mechanism results also suggest that different audio regions contribute differently to detection, which supports H1: if ML-generated audio has different regional statistical properties, attention-weighted classifiers may respond differently.

---

## ML Audio Generation Models

### [8] van den Oord et al. — "WaveNet: A generative model for raw audio" (arXiv, 2016)

**Why it's relevant:** Foundational paper establishing autoregressive neural audio generation. WaveNet generates audio sample-by-sample using dilated causal convolutions, producing highly natural speech.

**What we use from it:** WaveNet is the vocoder underlying many TTS systems (including Tacotron 2). We reference it to explain *why* ML-generated audio has different statistical properties: autoregressive generation imposes sequential dependencies and a learned sample-level distribution that differs from the natural acoustic process. This is core to our theoretical motivation — the statistical fingerprint WaveNet imposes is what we hypothesize will interact with steganographic embedding.

---

### [9] Shen et al. — "Natural TTS synthesis by conditioning WaveNet on mel spectrogram predictions" (IEEE ICASSP, 2018)

**Why it's relevant:** Describes Tacotron 2, the end-to-end TTS system combining a sequence-to-sequence mel-spectrogram predictor with a WaveNet vocoder. Achieved MOS 4.53 (vs. 4.58 for real recordings).

**What we use from it:** The near-human MOS score establishes that Tacotron 2-class systems produce audio that is *perceptually* indistinguishable from real speech — making the question of *statistical* distinguishability (relevant for steganalysis) both non-obvious and important. Their architecture description informs our choice of Coqui TTS (which uses a similar seq2seq + vocoder pipeline) as one of our generation models.

---

### [10] Liu et al. — "AudioLDM: Text-to-audio generation with latent diffusion models" (ICML, 2023)

**Why it's relevant:** Represents the diffusion paradigm in audio generation — fundamentally different from autoregressive models. Uses latent diffusion with CLAP embeddings for text-to-audio generation.

**What we use from it:** AudioLDM is referenced to motivate why we test multiple generation architectures: diffusion models produce audio through iterative denoising rather than sequential prediction, yielding different noise residual patterns and spectral characteristics. Even though we primarily use Bark and Coqui TTS in our experiments (due to local M4 Pro feasibility), AudioLDM represents the broader landscape of generation approaches that our findings should generalize to. If time permits, we may add it as a third generation model.

---

## Steganography in AI-Generated Media

### [11] Li, Wang & Jia — "A coverless audio steganography based on generative adversarial networks" (Electronics, 2023)

**Why it's relevant:** Demonstrates the intersection of AI audio generation and steganography — uses WaveGAN to synthesize stego-audio directly (coverless steganography).

**What we use from it:** This paper is important for positioning our work. Li et al. use AI generation *as* the embedding mechanism (the GAN is trained to produce audio that encodes a message). Our study is different: we use AI-generated audio *as a passive carrier* for traditional embedding methods. We cite this to show that while the AI-steganography intersection is being explored, the specific question of how pre-generated ML audio behaves as a carrier — without modifying the generation process — remains unanswered.

---

### [12] Chang & Echizen — "Steganography beyond space-time with chain of multimodal AI" (Scientific Reports, 2025)

**Why it's relevant:** Very recent work (2025) exploring steganography through multimodal AI reconstruction of audiovisual content — embedding messages in the linguistic domain rather than the signal domain.

**What we use from it:** We cite this as evidence that the convergence of AI generation and steganography is an active frontier. Their finding that multimodal AI pipelines can preserve hidden information across modality transformations (text → speech → text) suggests that AI-generated audio has structural properties relevant to information hiding. This supports our broader motivation that understanding how AI-generated audio interacts with steganography is a timely research question.

---

## Audio Deepfake Detection

### [13] Zhang et al. — "Where are we in audio deepfake detection? A systematic analysis" (arXiv, 2024)

**Why it's relevant:** SONAR — a comprehensive 2024 benchmark evaluating 9 TTS/generation platforms against 6 detection models. Directly addresses the statistical distinguishability of ML-generated vs. real audio.

**What we use from it:** This is critical for H4 (cross-domain degradation) and H5 (asymmetric transfer). Their key finding — that detection models struggle with cross-platform generalization (training on one TTS system, testing on another) — directly parallels our cross-domain steganalysis experiments. If deepfake detectors can't generalize across generation methods, we predict steganalysis classifiers will similarly struggle across the real/ML-generated boundary. Their evaluation protocol (ROC-AUC, EER) also aligns with our metrics.

---

## Core Embedding Theory

### [14] Chen & Wornell — "Quantization index modulation" (IEEE Trans. Information Theory, 2001)

**Why it's relevant:** Foundational paper establishing QIM as a theoretically principled framework for information embedding, with provable distortion–rate bounds.

**What we use from it:** QIM underpins our DCT-based embedding implementation. We use a "QIM-inspired scheme" (Section 4.3) where DCT coefficients are quantized with different codebooks depending on the message bit. Chen and Wornell's distortion analysis provides the theoretical justification for why DCT embedding achieves a better capacity–imperceptibility trade-off than naïve coefficient replacement. Their framework also helps us predict H3 (method sensitivity): because QIM operates on coefficient distributions directly shaped by the generative process, carrier origin should matter more for DCT than for LSB.

---

## Datasets

### [15] Panayotov et al. — "LibriSpeech: An ASR corpus based on public domain audio books" (IEEE ICASSP, 2015)

**Why it's relevant:** LibriSpeech is the standard large-scale English speech corpus (1,000 hours, 16 kHz, ~2,500 speakers) widely used in both ASR and audio ML research.

**What we use from it:** LibriSpeech serves as our **primary real audio source** (Section 4.2). We sample 500 clips from it for the real carrier dataset. Its advantages: publicly available, well-characterized acoustics, large speaker pool (enables stratified cross-validation by speaker to prevent data leakage), and 16 kHz sample rate matching typical TTS output. Many TTS models were also trained on LibriSpeech, creating a controlled comparison — the ML-generated audio will have been trained on (or similar to) the same distribution as our real dataset.

---

## Summary: Reference Coverage by Research Question

| Research Question | Key References |
|---|---|
| **Primary RQ** (carrier source → detectability) | [1], [3], [4]–[7], [11], [12] |
| **RQ1** (payload sensitivity) | [1], [2], [5], [7] |
| **RQ2** (LSB vs. DCT × carrier source) | [2], [4], [6], [14] |
| **RQ3** (cross-domain generalization) | [3], [5], [6], [13] |
| **Motivation / research gap** | [8]–[12], [13] |
| **Methodology** | [4], [6], [14], [15] |
