# Mini Report: Model Quality Gate Failure in Jenkins CI/CD

## 1. Context and Objective

This mini report documents a real CI/CD execution outcome in the MLOps pipeline, where model training completed successfully but deployment was blocked by a model quality gate.

The objective of this step is to verify that the pipeline enforces a performance threshold before allowing downstream delivery stages.

---

## 2. Pipeline Stage Under Analysis

The analyzed stage is:

- `MLOps Train + Evaluate Gate (main)` in the Jenkins pipeline.

This stage performs:

1. Model training on a CI sample.
2. Evaluation on holdout data.
3. Quality gate validation using weighted F1 score.

---

## 3. Observed Execution Evidence

From Jenkins logs:

- Training finished normally (`Training completed after 1 iterations`).
- Evaluation metrics were generated successfully.
- Final gate summary showed:
  - `f1 = 0.2014707645577715`
  - `threshold = 0.30`
  - `passed = false`
- Pipeline then returned `exit code 1`.
- `CD Serve + Docs (main push)` was skipped due to earlier failure.

This confirms the build failed because of model quality, not infrastructure.

---

## 4. Root Cause Analysis

The root cause is **insufficient model performance relative to the configured acceptance criterion**:

- Required minimum F1: `0.30`
- Achieved F1: `0.20147`

Since the measured metric is below threshold, the quality gate correctly rejected the candidate model.

---

## 5. Why This Failure Is Correct (MLOps Perspective)

This is an expected and desirable behavior in a production-oriented MLOps workflow:

1. It prevents low-quality models from propagating to serving/deployment stages.
2. It transforms CI/CD from pure code validation to **model-aware governance**.
3. It enforces objective acceptance criteria and improves release reliability.

In other words, this failure is a successful demonstration of quality control, not a pipeline defect.

---

## 6. Corrective Action Implemented

To improve model performance while preserving strict governance:

- The gate threshold was kept at `0.30`.
- CI training effort was increased in `Jenkinsfile`:
  - `CI_NUM_SAMPLES = 256`
  - `CI_NUM_EPOCHS = 3`
  - `CI_BATCH_SIZE = 16`

This approach strengthens model learning rather than weakening acceptance standards.

---

## 7. Academic Interpretation

The result demonstrates a key MLOps principle:

- **A deployment pipeline must validate both software correctness and model quality.**

The observed failure proves the project has moved beyond basic DevOps automation and now includes measurable ML performance gates for release decisions.

---

## 8. Conclusion

The CI/CD execution is functioning as intended. The pipeline correctly blocked progression because the evaluated model did not satisfy the required F1 threshold. This event provides strong evidence that the project implements practical MLOps quality governance.

