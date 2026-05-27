default:
    @just --list

# Commit current work to master, verify, and push to ejconlon/master.
ship msg="fixes":
    #!/usr/bin/env bash
    set -euo pipefail

    if git remote get-url ejconlon >/dev/null 2>&1; then
        git remote set-url ejconlon git@github.com:ejconlon/glo.git
    else
        git remote add ejconlon git@github.com:ejconlon/glo.git
    fi

    git switch -C master HEAD
    git add -A
    if ! git diff --cached --quiet; then
        git commit -m {{quote(msg)}}
    fi

    git merge origin/master --no-edit
    test/integration.sh
    git push ejconlon master
    git fetch origin master
