#!/usr/bin/env bash
# Builds openpyxl-layer.zip, ready to upload as a Lambda layer.
# Run this on a machine with Python 3.12 (or use a matching Docker image so the
# compiled dependencies match the Lambda runtime).
set -euo pipefail

rm -rf layer_build openpyxl-layer.zip
mkdir -p layer_build/python
pip install -r requirements.txt -t layer_build/python
cd layer_build
zip -r ../openpyxl-layer.zip python
cd ..
rm -rf layer_build

echo "Built openpyxl-layer.zip - upload this as a new Lambda layer (Python 3.12 runtime)."
