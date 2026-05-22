pipeline {
    agent any
    triggers {
        githubPush()
        // Fallback trigger: detect remote changes every 2 minutes
        pollSCM('H/2 * * * *')
    }
    options {
        timestamps()
        disableConcurrentBuilds()
    }
    environment {
        PYTHON = 'python'
        VENV_DIR = 'venv'
        // ===== ADDED: CI artifacts and quality gate settings (START) =====
        RESULTS_DIR = 'artifacts'
        F1_THRESHOLD = '0.30'
        CI_NUM_SAMPLES = '256'
        CI_NUM_EPOCHS = '3'
        CI_BATCH_SIZE = '16'
        // ===== ADDED: CI artifacts and quality gate settings (END) =====
    }
    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Setup Python') {
            steps {
                bat """
                %PYTHON% -m venv %VENV_DIR%
                call %VENV_DIR%\\Scripts\\activate
                REM ===== ADDED: Stabilize packaging toolchain for Ray/pkg_resources (START) =====
                python -m pip install --upgrade pip
                pip install -r requirements.txt
                python -m pip install "setuptools==65.7.0" "wheel==0.41.2"
                python -c "from pkg_resources._vendor.packaging.version import parse; print('pkg_resources._vendor OK')"
                REM ===== ADDED: Stabilize packaging toolchain for Ray/pkg_resources (END) =====
                """
            }
        }
        stage('CI Workloads (PR validation)') {
            when {
                expression { env.CHANGE_ID }   // Runs only for Pull Request builds
            }
            steps {
                bat """
                call %VENV_DIR%\\Scripts\\activate
                python -m madewithml.train --help
                python -m madewithml.evaluate --help
                """
            }
        }
        // ===== ADDED: MLOPS TRAIN + EVALUATE GATE (START) =====
        stage('MLOps Train + Evaluate Gate (PR)') {
            when {
                expression { env.CHANGE_ID }   // PR only
            }
            steps {
                bat """
                call %VENV_DIR%\\Scripts\\activate
                if not exist %RESULTS_DIR% mkdir %RESULTS_DIR%
                REM ===== ADDED: Ensure project root is importable for helper script (START) =====
                set PYTHONPATH=%CD%
                REM ===== ADDED: Ensure project root is importable for helper script (END) =====
                python scripts\\ci_train_eval_gate.py --dataset datasets/dataset.csv --holdout datasets/holdout.csv --results-dir %RESULTS_DIR% --num-samples %CI_NUM_SAMPLES% --num-epochs %CI_NUM_EPOCHS% --batch-size %CI_BATCH_SIZE% --f1-threshold %F1_THRESHOLD%
                """
            }
        }

        stage('MLOps Train + Evaluate Gate (main)') {
            when {
                allOf {
                    // ===== ADDED: Classic pipeline main-branch detection (START) =====
                    expression { (env.GIT_BRANCH ?: '').contains('origin/main') }
                    // ===== ADDED: Classic pipeline main-branch detection (END) =====
                    expression { !env.CHANGE_ID }   // main push (not PR)
                }
            }
            steps {
                bat """
                call %VENV_DIR%\\Scripts\\activate
                if not exist %RESULTS_DIR% mkdir %RESULTS_DIR%
                REM ===== ADDED: Ensure project root is importable for helper script (START) =====
                set PYTHONPATH=%CD%
                REM ===== ADDED: Ensure project root is importable for helper script (END) =====
                python scripts\\ci_train_eval_gate.py --dataset datasets/dataset.csv --holdout datasets/holdout.csv --results-dir %RESULTS_DIR% --num-samples %CI_NUM_SAMPLES% --num-epochs %CI_NUM_EPOCHS% --batch-size %CI_BATCH_SIZE% --f1-threshold %F1_THRESHOLD%
                """
            }
        }
        // ===== ADDED: MLOPS TRAIN + EVALUATE GATE (END) =====

        stage('CD Serve + Docs (main push)') {
            when {
                allOf {
                    // ===== ADDED: Classic pipeline main-branch detection (START) =====
                    expression { (env.GIT_BRANCH ?: '').contains('origin/main') }
                    // ===== ADDED: Classic pipeline main-branch detection (END) =====
                    expression { !env.CHANGE_ID }   // Push to main (not PR)
                }
            }
            steps {
                bat """
                call %VENV_DIR%\\Scripts\\activate
                set PYTHONPATH=%CD%
                python scripts\\ci_deploy_smoke.py --summary artifacts\\quality_gate_summary.json --report artifacts\\deploy_smoke.json --metrics-report artifacts\\metrics_smoke.txt --backend fastapi
                if errorlevel 1 exit /b 1
                mkdocs build --strict
                if errorlevel 1 exit /b 1
                echo Deploy smoke + docs build completed.
                """
            }
        }
        stage('Monitoring Rules + Act (main push)') {
            when {
                allOf {
                    expression { (env.GIT_BRANCH ?: '').contains('origin/main') }
                    expression { !env.CHANGE_ID }
                }
            }
            steps {
                bat """
                call %VENV_DIR%\\Scripts\\activate
                setlocal EnableExtensions EnableDelayedExpansion
                if not exist artifacts\\monitoring mkdir artifacts\\monitoring
                if not exist artifacts\\alerts mkdir artifacts\\alerts
                echo [MON] cwd=%CD%
                echo [MON] artifacts tree before monitoring:
                dir artifacts

                REM ===== ADDED: Expectations validation for monitoring (START) =====
                echo [MON] running monitor_expectations
                where python
                %VENV_DIR%\\Scripts\\python.exe -c "import sys; print('exe=', sys.executable); print('ver=', sys.version)"
                %VENV_DIR%\\Scripts\\python.exe -c "import great_expectations as ge; print('GE=', ge.__version__)"
                %VENV_DIR%\\Scripts\\python.exe -c "import pandas as pd; print('pandas=', pd.__version__)"
                %VENV_DIR%\\Scripts\\python.exe -X faulthandler -u scripts\\monitor_expectations.py --input datasets\\holdout.csv --output artifacts\\monitoring\\expectations_report.json
                set RC=!ERRORLEVEL!
                echo [MON] raw monitor_expectations errorlevel=!RC!
                if exist artifacts\\monitoring\\expectations_report.json (
                    echo [MON] ----- BEGIN expectations_report.json -----
                    type artifacts\\monitoring\\expectations_report.json
                    echo [MON] ----- END expectations_report.json -----
                ) else (
                    echo [MON][ERROR] Missing artifacts\\monitoring\\expectations_report.json
                    exit /b 31
                )
                %VENV_DIR%\\Scripts\\python.exe -c "import json,sys; d=json.load(open(r'artifacts\\monitoring\\expectations_report.json', encoding='utf-8')); sys.exit(0 if d.get('success') else 1)"
                set RC_REPORT=!ERRORLEVEL!
                echo [MON] expectations_report success rc=!RC_REPORT!
                if not "!RC_REPORT!"=="0" exit /b 32
                if not "!RC!"=="0" echo [MON][WARN] monitor_expectations nonzero rc with success report
                echo [MON] monitor_expectations rc=!RC!
                REM ===== ADDED: Expectations validation for monitoring (END) =====

                REM ===== ADDED: Sliding-window monitoring metrics (START) =====
                echo [MON] checking artifacts\\eval_results.json
                if exist artifacts\\eval_results.json (
                    echo [MON] found artifacts\\eval_results.json
                    for %%I in (artifacts\\eval_results.json) do echo [MON] eval_results size=%%~zI bytes modified=%%~tI
                    echo [MON] ----- BEGIN eval_results.json -----
                    type artifacts\\eval_results.json
                    echo [MON] ----- END eval_results.json -----
                    %VENV_DIR%\\Scripts\\python.exe -u scripts\\monitor_sliding_metrics.py --input artifacts\\eval_results.json --output artifacts\\monitoring\\performance_timeseries.json --window-size 24
                    set RC=!ERRORLEVEL!
                    echo [MON] monitor_sliding_metrics rc=!RC!
                    if not "!RC!"=="0" exit /b !RC!
                ) else (
                    echo [MON][ERROR] Missing artifacts\\eval_results.json for sliding metrics.
                    echo [MON] artifacts tree when missing eval_results:
                    dir artifacts
                    exit /b 20
                )
                REM ===== ADDED: Sliding-window monitoring metrics (END) =====

                REM ===== ADDED: Alerting rules + Act workflow (START) =====
                %VENV_DIR%\\Scripts\\python.exe -u scripts\\monitor_alerts.py --drift-log logs\\error.log --performance artifacts\\monitoring\\performance_timeseries.json --output artifacts\\alerts\\latest_alert.json
                set RC=!ERRORLEVEL!
                echo [MON] monitor_alerts rc=!RC!
                if not "!RC!"=="0" if not "!RC!"=="1" exit /b !RC!
                %VENV_DIR%\\Scripts\\python.exe -u scripts\\monitor_act.py --alert artifacts\\alerts\\latest_alert.json --expectations artifacts\\monitoring\\expectations_report.json --output artifacts\\alerts\\action_decision.json --trigger-file artifacts\\alerts\\retrain.trigger
                set RC=!ERRORLEVEL!
                echo [MON] monitor_act rc=!RC!
                if not "!RC!"=="0" if not "!RC!"=="1" exit /b !RC!
                REM ===== ADDED: Alerting rules + Act workflow (END) =====
                """
            }
        }
    }
    post {
        always {
            // ===== ADDED: Archive gate outputs for review (START) =====
            archiveArtifacts artifacts: 'Jenkinsfile, requirements.txt, artifacts/*.json, artifacts/*.txt, artifacts/monitoring/*.json, artifacts/alerts/*.json, site/**', allowEmptyArchive: true            
            // ===== ADDED: Archive gate outputs for review (END) =====
        }
        success {
            echo 'Pipeline finished successfully.'
        }
        failure {
            echo 'Pipeline failed. Check stage logs for root cause.'
        }
    }
}
