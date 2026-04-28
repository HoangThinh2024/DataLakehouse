#!/bin/bash
# Real-time Data Watcher for DataLakehouse (Docker Volume Edition)
# Monitors bronze folder inside the container and triggers Mage AI.

PIPELINE_UUID="etl_excel_to_lakehouse"

echo "[Watcher] Starting Docker-aware monitor on rustfs/bronze..."

last_state=""

while true; do
    # Check files inside the docker container
    current_state=$(docker exec dlh-rustfs ls -lR /data/bronze | grep ".xlsx")
    
    if [ "$current_state" != "$last_state" ] && [ -n "$current_state" ]; then
        echo "[Watcher] New activity in RustFS Bronze! Triggering Pipeline..."
        docker exec dlh-mage mage run /home/src "$PIPELINE_UUID"
        last_state="$current_state"
        echo "[Watcher] Run complete. Waiting for next change..."
    fi
    
    sleep 10
done
