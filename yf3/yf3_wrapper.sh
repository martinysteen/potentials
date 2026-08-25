#!/bin/bash
# The purpose of this script is to allow some sh to run on a fixed time in UTC+1 (winter) and UTC+2 (summer)
# Cronjob execution can be listed by 'crontab -l' and edited with 'crontab -e'

# Get current local hour with explicit timezone
export TZ=Europe/Berlin
LOGFILE=/home/sm/logs/yf3_wrapper.log

# Start logging
{

# Get local hour (24h format)
LOCAL_HOUR=$(date +%H)
# echo "yf3_wrapper.sh now in touch: $(date) $LOCAL_HOUR"

# MULTIPLE TARGET HOURS - Test different execution times
# Add or remove hours as needed for testing
# TARGET_HOURS=(02 05 08 10 12 15)
# indtil 19.3.26 kl 14: TARGET_HOURS=(02 08 15)
# indtil 24.8.26: TARGET_HOURS=(02)
# 24.8.26: trialing an evening fetch (22) alongside the night one (02), to sidestep
# the ASX/HK/SS open-boundary ambiguity the 02:xx window sits on top of -- see
# MAINTENANCE.md. Both run for now; one will be dropped once SM has compared them.
TARGET_HOURS=(02 22)

# Check if current hour matches any target hour
SHOULD_RUN=false
for TARGET_HOUR in "${TARGET_HOURS[@]}"; do
  if [ "$LOCAL_HOUR" -eq "$TARGET_HOUR" ]; then
    SHOULD_RUN=true
    # echo "[MATCH] Current hour ($LOCAL_HOUR) matches target hour ($TARGET_HOUR)"
    break
  fi
done

if [ "$SHOULD_RUN" = true ]; then
  echo "========================================="
  echo "yf3_wrapper.sh now in active mode: $(date) $LOCAL_HOUR"
  echo "[OK] Target local hour matched. Starting scripts..."
  
  # Run yf3 script
  echo "-----------------------------------"
  echo "[START] Running start_yf3.sh at $(date)"
  bash /home/sm/potentials/yf3/start_yf3.sh
  YF3_EXIT_CODE=$?
  echo "[END] start_yf3.sh finished with exit code: $YF3_EXIT_CODE at $(date)"
  
  if [ $YF3_EXIT_CODE -eq 0 ]; then
    echo "[SUCCESS] yf3 script completed successfully"
    
    # Log success with timestamp to separate success log
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Hour: $LOCAL_HOUR - SUCCESS - Exit: $YF3_EXIT_CODE" >> /home/sm/logs/yf3_timing_results.log
  else
    echo "[ERROR] yf3 script failed with exit code: $YF3_EXIT_CODE"
    
    # Log failure
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Hour: $LOCAL_HOUR - FAILED - Exit: $YF3_EXIT_CODE" >> /home/sm/logs/yf3_timing_results.log
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

  echo "yf3_wrapper.sh leaving active mode: $(date) $LOCAL_HOUR"
  echo "========================================="
  
else
  # echo "[SKIP] Current hour ($LOCAL_HOUR) does not match any target hours (${TARGET_HOURS[@]}). Skipping execution."
  :
fi

} >> "$LOGFILE" 2>&1
