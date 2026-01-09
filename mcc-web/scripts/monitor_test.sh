#!/bin/bash
# Continuous monitoring script for the extended cronjob test

TEST_LOG="/tmp/extended_cronjob_test.log"
CHECK_INTERVAL=60  # Check every 60 seconds

echo "Monitoring extended cronjob test..."
echo "Press Ctrl+C to stop monitoring"
echo ""

while true; do
    PID=$(ps aux | grep "[r]un_extended_cronjob_test" | awk '{print $2}')
    
    if [ -z "$PID" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ❌ Test is NOT running"
        echo "Last log entries:"
        tail -20 "$TEST_LOG" 2>/dev/null || echo "No log file found"
        echo ""
        echo "Test may have completed or crashed. Check the log file for details."
        break
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Test is running (PID: $PID)"
        # Show last line of log
        tail -1 "$TEST_LOG" 2>/dev/null | head -1
    fi
    
    sleep $CHECK_INTERVAL
done

