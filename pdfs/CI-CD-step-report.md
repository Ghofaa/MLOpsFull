# CI/CD Implementation Report for MLOps Project

## 1. Introduction

This report documents the CI/CD implementation step for the `MLOpsFull-1` project using Jenkins.  
The objective of this phase is to automate validation and delivery activities so that machine learning application changes are tested before integration and prepared for deployment after merge.

The implementation follows the course requirement from the CI/CD lesson:

- Trigger **workload validation** when a Pull Request targets `main`.
- Trigger **serving/deployment workflow** when changes are pushed to `main`.

This event-driven workflow creates a controlled path from experimentation to production.

---

## 2. Project Context

The repository contains an ML application module (`madewithml`) with key workloads:

- `madewithml.train` for model training.
- `madewithml.evaluate` for evaluation.
- `madewithml.serve` for serving/prediction API behavior.

The dependency set in `requirements.txt` is heavily version-pinned. While this improves reproducibility, it also introduces compatibility constraints across Python versions. During setup, these constraints became an important operational consideration for CI agents.

---

## 3. Objectives of This Step

The CI/CD step was designed to meet the following technical and process objectives:

1. Create a reproducible build environment in Jenkins.
2. Separate validation logic (CI) from deployment logic (CD).
3. Run automated checks on Pull Requests before merge.
4. Run production-oriented workflow only after approved integration to `main`.
5. Improve traceability through stage logs and post-build reporting.

---

## 4. Pipeline Design and Architecture

The pipeline is implemented in a declarative `Jenkinsfile` and includes:

### 4.1 Global Pipeline Controls

- `agent any`: allows execution on available Jenkins workers.
- `timestamps()`: improves auditability and debugging by timestamping logs.
- `disableConcurrentBuilds()`: prevents overlapping builds on the same branch.

### 4.2 Environment Setup Strategy

- Create virtual environment at runtime.
- Upgrade packaging tooling (`pip`, `setuptools`, `wheel`).
- Install project dependencies from `requirements.txt`.

This ensures each build starts from a clean and controlled software environment.

### 4.3 Stage Model

- **Checkout**: retrieve source code.
- **Setup Python**: provision environment and install dependencies.
- **CI Workloads (PR validation)**: run only for Pull Request builds.
- **CD Serve + Docs (main push)**: run only for push events on `main`.
- **Post actions**: archive build artifacts and emit final status.

### 4.4 Event-Driven Logic

Conditional stage execution is used to enforce branch/event policy:

- PR context (`CHANGE_ID` present) -> run CI validation stage.
- `main` branch push (not PR) -> run CD stage.

This mirrors common DevOps practice: validate before merge, release after merge.

---

## 5. Implementation Workflow (What Was Done)

The following sequence was followed to implement and validate this step:

1. Reviewed CI/CD lesson requirements to map expected event triggers.
2. Inspected repository structure and workload entry points.
3. Designed Jenkins stages to match both technical project structure and lesson expectations.
4. Added conditional execution to separate PR and `main` behavior.
5. Prepared post-build feedback and artifact archiving for visibility.

The resulting Jenkins pipeline provides a minimal but complete CI/CD skeleton suitable for extension in later phases (monitoring, quality gates, production deployment).

---

## 6. Technical Challenges and Root Cause Analysis

During environment setup and dependency installation, multiple errors were encountered.  
The observed issues and causes are summarized below.

### 6.1 Shell Activation Issue

Initial virtual environment activation used `source`, which is a Bash command.  
On Windows PowerShell, activation must use `.\venv\Scripts\Activate.ps1`.

**Impact:** setup failure before dependency installation.

### 6.2 Missing Build Backend (`setuptools.build_meta`)

An early install attempt failed with:

- `BackendUnavailable: Cannot import 'setuptools.build_meta'`

**Cause:** incomplete or outdated build tooling in the virtual environment.  
**Resolution:** upgrade `pip`, `setuptools`, and `wheel`.

### 6.3 Python Version Incompatibility (3.12)

Pinned dependencies (for example `numpy==1.24.3`) conflicted with Python 3.12 and older build chains, producing errors such as removed standard-library API references.

**Cause:** package ecosystem mismatch between modern interpreter and older pinned stack.

### 6.4 Python Version Incompatibility (3.11 Transitive)

Even after moving to Python 3.11, transitive dependencies (notably around older `pyarrow`) requested `numpy==1.21.3`, which does not support Python 3.11.

**Cause:** deep dependency graph constraints in legacy-pinned ML stack.

### 6.5 Practical Compatibility Conclusion

For this exact pinned requirements set, **Python 3.10** is the most stable runtime target for local setup and Jenkins agents.

---

## 7. Why This CI/CD Design Is Correct

This design is correct and appropriate for the assignment for the following reasons:

1. **Direct requirement alignment**: PR triggers workload checks; main push triggers serving/deployment workflow.
2. **Risk control**: unvalidated code is less likely to reach deployment stages.
3. **Reproducibility**: clean environment provisioning per build.
4. **Traceability**: stage-level logs and final status support demonstration and debugging.
5. **Extensibility**: quality gates, docs publishing, monitoring hooks, and model promotion can be added incrementally.

---

## 8. Results and Deliverables

### 8.1 Deliverable Produced

- A functional Jenkins declarative pipeline in `Jenkinsfile` implementing CI/CD stage separation.

### 8.2 Observable Outcome

- Project now has an automated path:
  - code change -> PR validation -> merge -> main-branch delivery workflow.

### 8.3 Educational Outcome

- Demonstrates practical MLOps transition from manual operations to controlled automation.

---

## 9. Limitations

The current step is foundational and intentionally lightweight. Remaining limitations include:

- CD stage is a controlled placeholder and may need real deployment commands depending on infrastructure.
- No metric-based quality gate yet (for example, automatic failure if F1 drops).
- Dependency set remains old and sensitive to Python/runtime changes.
- External services (artifact registry, model registry policies, monitoring backends) are not yet fully integrated in this step.

---

## 10. Recommended Next Steps

To strengthen the pipeline for later project phases:

1. Add real train/evaluate execution with dataset parameters.
2. Add model quality gate (minimum acceptable metric threshold).
3. Add documentation build stage (`mkdocs build`) and optional publish stage.
4. Introduce structured test reports and coverage publishing.
5. Pin Jenkins agents to Python 3.10 or modernize dependency pins to support newer runtimes.
6. Add deployment environment separation (staging vs production).
7. Integrate monitoring and regression triggers as described in continual-learning workflows.

---

## 11. Conclusion

This CI/CD step successfully establishes an event-driven Jenkins workflow aligned with course requirements and MLOps best practices.  
It provides a strong baseline for continual learning systems by enforcing pre-merge validation and post-merge delivery behavior.  
Despite dependency compatibility constraints, the step is operationally sound and ready for extension in subsequent project milestones.

---

## 12. Appendix: Short Presentation Script (Optional)

"In this phase, I implemented a Jenkins CI/CD pipeline for our ML application.  
The pipeline uses event-based triggers: Pull Requests to `main` run validation workloads, and pushes to `main` run serving/deployment workflow stages.  
This separation is important because it protects production from unvalidated model changes.  
I also handled real dependency compatibility issues and determined that Python 3.10 is the stable runtime for our pinned package set.  
Overall, this step transitions the project from manual execution to controlled, traceable automation, which is a core principle in MLOps."
