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
                python -m pip install --upgrade pip setuptools wheel
                pip install -r requirements.txt
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
                python scripts\\ci_train_eval_gate.py --dataset datasets/dataset.csv --holdout datasets/holdout.csv --results-dir %RESULTS_DIR% --num-samples 64 --num-epochs 1 --batch-size 16 --f1-threshold %F1_THRESHOLD%
                """
            }
        }

        stage('MLOps Train + Evaluate Gate (main)') {
            when {
                allOf {
                    branch 'main'
                    expression { !env.CHANGE_ID }   // main push (not PR)
                }
            }
            steps {
                bat """
                call %VENV_DIR%\\Scripts\\activate
                if not exist %RESULTS_DIR% mkdir %RESULTS_DIR%
                python scripts\\ci_train_eval_gate.py --dataset datasets/dataset.csv --holdout datasets/holdout.csv --results-dir %RESULTS_DIR% --num-samples 64 --num-epochs 1 --batch-size 16 --f1-threshold %F1_THRESHOLD%
                """
            }
        }
        // ===== ADDED: MLOPS TRAIN + EVALUATE GATE (END) =====

        stage('CD Serve + Docs (main push)') {
            when {
                allOf {
                    branch 'main'
                    expression { !env.CHANGE_ID }   // Push to main (not PR)
                }
            }
            steps {
                bat """
                call %VENV_DIR%\\Scripts\\activate
                python -m madewithml.serve --help
                """
                echo 'Main branch push detected: serve/docs deployment stage executed.'
            }
        }
    }
    post {
        always {
            // ===== ADDED: Archive gate outputs for review (START) =====
            archiveArtifacts artifacts: 'Jenkinsfile, requirements.txt, artifacts/*.json', allowEmptyArchive: true
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
