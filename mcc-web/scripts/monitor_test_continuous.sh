#!/bin/bash
# Continuous monitoring script for 30-minute extended cronjob test
# This script monitors the test and reports status every minute

TEST_LOG="/tmp/extended_cronjob_test_30min.log"
CHECK_INTERVAL=60  # Check every 60 seconds
START_TIME=$(date +%s)
EXPECTED_DURATION=1800  # 30 minutes in seconds

echo "=========================================="
echo "Monitoring 30-minute Extended Cronjob Test"
echo "=========================================="
echo "Started: $(date)"
echo "Log file: $TEST_LOG"
echo "Check interval: $CHECK_INTERVAL seconds"
echo "Expected duration: 30 minutes"
echo "=========================================="
echo ""

check_count=0
last_update_time=""
error_count=0

while true; do
    check_count=$((check_count + 1))
    current_time=$(date '+%Y-%m-%d %H:%M:%S')
    elapsed=$(($(date +%s) - START_TIME))
    elapsed_min=$((elapsed / 60))
    elapsed_sec=$((elapsed % 60))
    
    PID=$(ps aux | grep "[r]un_extended_cronjob_test" | awk '{print $2}')
    
    if [ -z "$PID" ]; then
        echo "[$current_time] ❌ Test is NOT running (after ${elapsed_min}m ${elapsed_sec}s)"
        echo ""
        echo "Last 30 lines of log:"
        tail -30 "$TEST_LOG" 2>/dev/null || echo "No log file found"
        echo ""
        
        # Check for errors
        errors=$(grep -i "error\|exception\|traceback\|failed" "$TEST_LOG" 2>/dev/null | wc -l)
        if [ "$errors" -gt 0 ]; then
            echo "⚠️  Found $errors error(s) in log:"
            grep -i "error\|exception\|traceback\|failed" "$TEST_LOG" 2>/dev/null | tail -5
            error_count=$errors
        else
            echo "✅ No errors found - test may have completed successfully"
        fi
        
        # Check if test completed
        if grep -q "Test completed successfully" "$TEST_LOG" 2>/dev/null; then
            echo ""
            echo "✅ Test completed successfully!"
            grep -A 20 "Test completed successfully" "$TEST_LOG" 2>/dev/null | head -25
        fi
        
        exit 1
    else
        # Get last update time from log
        last_log_time=$(tail -1 "$TEST_LOG" 2>/dev/null | grep -oP '\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}' | head -1 || echo "")
        
        # Count updates and cronjob runs
        total_updates=$(grep -c "Successfully processed update" "$TEST_LOG" 2>/dev/null || echo "0")
        cronjob_runs=$(grep -c "Cronjob run #" "$TEST_LOG" 2>/dev/null || echo "0")
        hourly_metrics=$(grep -c "HourlyMetric" "$TEST_LOG" 2>/dev/null || echo "0")
        
        # Check for new errors
        new_errors=$(grep -i "error\|exception\|traceback" "$TEST_LOG" 2>/dev/null | wc -l)
        if [ "$new_errors" -gt "$error_count" ]; then
            echo "[$current_time] ⚠️  NEW ERROR DETECTED!"
            grep -i "error\|exception\|traceback" "$TEST_LOG" 2>/dev/null | tail -3
            error_count=$new_errors
        fi
        
        # Show status
        if [ "$check_count" -eq 1 ] || [ "$((check_count % 5))" -eq 0 ]; then
            # Show detailed status every 5 minutes
            echo "[$current_time] ✅ Test running (PID: $PID) - Elapsed: ${elapsed_min}m ${elapsed_sec}s"
            echo "   Updates: $total_updates | Cronjob runs: $cronjob_runs | HourlyMetrics: $hourly_metrics"
            if [ -n "$last_log_time" ]; then
                echo "   Last activity: $last_log_time"
            fi
            echo ""
        else
            # Simple status every minute
            echo "[$current_time] ✅ Running (${elapsed_min}m ${elapsed_sec}s) - Updates: $total_updates, Cronjobs: $cronjob_runs"
        fi
        
        # Check if test should be done
        if [ $elapsed -gt $EXPECTED_DURATION ]; then
            echo ""
            echo "⏰ Expected duration exceeded. Test should be finishing soon..."
        fi
    fi
    
    sleep $CHECK_INTERVAL
done

