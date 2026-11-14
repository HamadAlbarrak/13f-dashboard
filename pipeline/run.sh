#!/bin/bash
# Full Q3 2026 13F universe rebuild. Run from this folder. Needs the 13f-analyzer skill installed (EDGAR client + contact header).
set -e
rm -rf books out; mkdir -p books out
python3 status.py
python3 pull.py
python3 analyze.py
python3 aggregate.py
python3 export.py
