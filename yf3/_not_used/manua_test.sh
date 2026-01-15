#!/bin/bash
# Quick manual test script to run yf3 multiple times today at different hours
# This is for IMMEDIATE testing without waiting for cron schedule

export TZ=Europe/Berlin
TEST_LOG="/home/sm/yf3_manual_test_$(date +%Y%m%d).log"

echo "=========================================" | tee -a "$TEST_LOG"
echo "Manual Multi-Hour Testing Started: $(date)" | tee -a "$TEST_LOG"
echo "=========================================" | tee -a "$TEST_LOG"
echo "" | tee -a "$TEST_LOG"

# Test hours to try (adjust based on current time)
TEST_HOURS=(2 5 8 10 14)
CURRENT_HOUR=$(date +%H)

echo "Current hour: $CURRENT_HOUR" | tee -a "$TEST_LOG"
echo "Will test the following hours: ${TEST_HOURS[@]}" | tee -a "$TEST_LOG"
echo "" | tee -a "$TEST_LOG"

# Option 1: Run immediately regardless of hour
echo "Option 1: Run immediate test now (ignoring hour check)" | tee -a "$TEST_LOG"
echo "Option 2: Wait and run at next scheduled test hour" | tee -a "$TEST_LOG"
echo "" | tee -a "$TEST_LOG"

# For immediate testing, run now
for i in {1..5}; do
    echo "=========================================" | tee -a "$TEST_LOG"
    echo "Test Run #$i at $(date)" | tee -a "$TEST_LOG"
    echo "=========================================" | tee -a "$TEST_LOG"
    
    # Run the yf3 script
    bash /home/sm/potentials/yf3/start_yf3.sh 2>&1 | tee -a "$TEST_LOG"
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[SUCCESS] Run #$i completed at $(date)" | tee -a "$TEST_LOG"
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Test Run $i - SUCCESS - Exit: $EXIT_CODE" >> /home/sm/yf3_manual_timing.log
    else
        echo "[FAILED] Run #$i failed at $(date) with exit code: $EXIT_CODE" | tee -a "$TEST_LOG"
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Test Run $i - FAILED - Exit: $EXIT_CODE" >> /home/sm/yf3_manual_timing.log
    fi
    
    # Wait 2 hours before next test (adjust as needed)
    if [ $i -lt 5 ]; then
        WAIT_TIME=7200  # 2 hours in seconds
        echo "" | tee -a "$TEST_LOG"
        echo "Waiting $((WAIT_TIME / 3600)) hours until next test..." | tee -a "$TEST_LOG"
        echo "Next test will be at: $(date -d "+$WAIT_TIME seconds")" | tee -a "$TEST_LOG"
        sleep $WAIT_TIME
    fi
done

echo "" | tee -a "$TEST_LOG"
echo "=========================================" | tee -a "$TEST_LOG"
echo "Manual testing completed: $(date)" | tee -a "$TEST_LOG"
echo "Results saved to: $TEST_LOG" | tee -a "$TEST_LOG"
echo "=========================================" | tee -a "$TEST_LOG"