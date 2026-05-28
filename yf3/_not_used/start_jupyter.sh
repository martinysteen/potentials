#!/bin/bash

# Kill any existing Jupyter processes before starting
pkill -f "jupyter lab"
sleep 2  # Wait for processes to terminate

# Kill anything using port 8888
fuser -k 8888/tcp 2>/dev/null

# Initialize conda
source ~/miniconda3/etc/profile.d/conda.sh

# Activate environment
conda activate yf3_env

# Adjust Jupyter's start folder
cd ~/potentials/yf3

# Start Jupyter Lab with fixed port
jupyter lab --port=8888 --no-browser --ServerApp.port_retries=0 --log-level=ERROR

# Keep the shell open after Jupyter exits
cd ~/
exec $SHELL

