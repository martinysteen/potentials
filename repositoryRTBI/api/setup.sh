#!/bin/bash
# Install API dependencies into the potsystem_env conda environment
conda activate potsystem_env
conda install -y -c conda-forge fastapi uvicorn python-dotenv pandas
