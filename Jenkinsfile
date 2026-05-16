pipeline {
    agent any
    options {
        timestamps()
        disableConcurrentBuilds()
    }
    environment {
        PYTHON = 'python'
        VENV_DIR = 'venv'
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
            archiveArtifacts artifacts: 'Jenkinsfile, requirements.txt', allowEmptyArchive: true
        }
        success {
            echo 'Pipeline finished successfully.'
        }
        failure {
            echo 'Pipeline failed. Check stage logs for root cause.'
        }
    }
}
