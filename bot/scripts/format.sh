#!/usr/bin/env bash

VENV_PATH=".venv"

if [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
else
    echo "virtual environment not found"
    exit 1
fi

if ! command -v isort &> /dev/null; then
    pip install isort~=7.0
fi

if ! command -v black &> /dev/null; then
    pip install black~=26.0
fi

isort .
black .
