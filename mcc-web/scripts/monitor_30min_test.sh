#!/bin/bash
# Monitoring script for 30-minute extended cronjob test

TEST_LOG="/tmp/extended_cronjob_test_30min.log"
CHECK_INTERVAL=30  # Check every 30 seconds
MAX_CHECKS=60      # Monitor for up to 35 minutes (60 * 30s = 30 min + buffer)

echo "=========================================="
echo "Monitoring 30-minute Extended Cronjob Test"
echo "=========================================="
echo "Log file: $TEST_LOG"
echo "Check interval: $CHECK_INTERVAL seconds"
echo "Press Ctrl+C to stop monitoring"
echo "=========================================="
echo ""

check_count=0
last_line_count=0

while [ $check_count -lt $MAX_CHECKS ]; do
    PID=$(ps aux | grep "[r]un_extended_cronjob_test" | awk '{print $2}')
    current_time=$(date '+%Y-%m-%d %H:%M:%S')
    
    if [ -z "$PID" ]; then
        echo "[$current_time] ❌ Test is NOT running"
        echo ""
        echo "Last 20 lines of log:"
        tail -20 "$TEST_LOG" 2>/dev/null || echo "No log file found"
        echo ""
        echo "Checking for errors..."
        if grep -i "error\|exception\|traceback\|failed" "$TEST_LOG" 2>/dev/null | tail -10; then
            echo ""
            echo "⚠️  Errors found in log!"
        else
            echo "✅ No errors found - test may have completed successfully"
        fi
        exit 1
    else
        # Count lines in log to detect progress
        current_line_count=$(wc -l < "$TEST_LOG" 2>/dev/null || echo "0")
        
        if [ "$current_line_count" -gt "$last_line_count" ]; then
            echo "[$current_time] ✅ Test running (PID: $PID) - Progress detected"
            # Show last meaningful line
            tail -1 "$TEST_LOG" 2>/dev/null | grep -v "^$" | head -1
            last_line_count=$current_line_count
        else
            echo "[$current_time] ✅ Test running (PID: $PID) - Waiting..."
        fi
        
        # Check for errors in log
        if grep -qi "error\|exception\|traceback" "$TEST_LOG" 2>/dev/null | tail -1; then
            echo "⚠️  Potential error detected in log!"
            tail -5 "$TEST_LOG"
        fi
    fi
    
    check_count=$((check_count + 1))
    sleep $CHECK_INTERVAL
done

echo ""
echo "Monitoring period completed. Test may still be running."
echo "Final status:"
ps aux | grep "[r]un_extended_cronjob_test" | grep -v grep && echo "✅ Test still running" || echo "❌ Test finished"

