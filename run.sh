#!/bin/bash
set -e

echo "=== Safety Chat Bot Installer ==="

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "Error: git is not installed. Please install git first."
    exit 1
fi

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: docker is not installed. Please install docker first."
    exit 1
fi

# Clone or pull repo
if [ ! -d "safety-chat-bot" ]; then
    echo "Cloning repository..."
    git clone https://github.com/weby-homelab/safety-chat-bot.git
    cd safety-chat-bot
else
    echo "Repository folder already exists, entering and updating..."
    cd safety-chat-bot
    git fetch --all
    git reset --hard origin/master
fi

# Set up .env
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please configure the variables in the .env file and then run: docker compose up -d"
else
    echo ".env file already exists. Starting containers..."
    docker compose up -d --build
fi
