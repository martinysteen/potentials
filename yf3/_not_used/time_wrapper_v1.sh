#!/bin/bash
# The purpose of this script is to allow some sh to run on a fixed time in UTC+1 (winter) and UTC+2 (summer)
# Cronjob execution can be listed by 'crontab -l' and edited with 'crontab -e'

# Get current local hour with explicit timezone
export TZ=Europe/Berlin
LOGFILE=/home/sm/time_wrapper.log

# Delete log file if it exists
#if [ -f "$LOGFILE" ]; then
#    rm "$LOGFILE"
#fi

# Start logging
{
echo "========================================="
echo "time_wrapper.sh start: $(date)"

# Get local hour (24h format)
LOCAL_HOUR=$(date +%H)
echo "Detected local hour: $LOCAL_HOUR" 

# Only run if it's NN:xx local time
# Caller shall offer UTC hours from N-2 to N 
# Best for yFinance is TARGET_HOUR=23 - fires 21.xx-23.xx dept summer/winter
# Next to this is TARGET_HOUR=07 - need fires 05:xx-07:xx UTC
# sm 3.10.25: crontab 23,0
TARGET_HOUR=02

if [ "$LOCAL_HOUR" -eq "$TARGET_HOUR" ]; then
  echo "[OK] Target local hour matched ($TARGET_HOUR). Starting scripts..."
  
  # Run yf3 script
  echo "-----------------------------------"
  echo "[START] Running start_yf3.sh at $(date)"
  bash /home/sm/potentials/yf3/start_yf3.sh
  YF3_EXIT_CODE=$?
  echo "[END] start_yf3.sh finished with exit code: $YF3_EXIT_CODE at $(date)"
  
  if [ $YF3_EXIT_CODE -eq 0 ]; then
    echo "[SUCCESS] yf3 script completed successfully"
  else
    echo "[ERROR] yf3 script failed with exit code: $YF3_EXIT_CODE"
  fi
  
  # Run Google Drive update
  echo "-----------------------------------"
  echo "[START] Updating Google Drive at $(date)"
  bash /home/sm/potentials/yf3/updgd_yf3.sh
  GD_EXIT_CODE=$?
  echo "[END] Google Drive update finished with exit code: $GD_EXIT_CODE at $(date)"
  
  if [ $GD_EXIT_CODE -eq 0 ]; then
    echo "[SUCCESS] Google Drive update completed successfully"
  else
    echo "[ERROR] Google Drive update failed with exit code: $GD_EXIT_CODE"
  fi
  
else
  echo "[SKIP] Current hour ($LOCAL_HOUR) does not match target hour ($TARGET_HOUR). Skipping execution."
fi

echo "time_wrapper.sh END: $(date)"
echo "========================================="

} >> "$LOGFILE" 2>&1