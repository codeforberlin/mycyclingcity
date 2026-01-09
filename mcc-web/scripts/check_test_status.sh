#!/bin/bash
# Script to check if the extended cronjob test is running

TEST_LOG="/tmp/extended_cronjob_test.log"
PID=$(ps aux | grep "run_extended_cronjob_test" | grep -v grep | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "❌ Test is NOT running"
    echo ""
    echo "Last log entries:"
    tail -20 "$TEST_LOG" 2>/dev/null || echo "No log file found"
    exit 1
else
    echo "✅ Test is running (PID: $PID)"
    echo ""
    echo "Last log entries:"
    tail -10 "$TEST_LOG" 2>/dev/null || echo "No log file found"
    echo ""
    echo "To monitor continuously:"
    echo "  tail -f $TEST_LOG"
    exit 0
fi

