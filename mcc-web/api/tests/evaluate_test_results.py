# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    evaluate_test_results.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Automated test result evaluation script.

Parses test output and generates a comprehensive evaluation report.
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime


def parse_test_output(output_text):
    """Parse test output and extract results."""
    results = {
        'total_tests': 0,
        'passed': 0,
        'failed': 0,
        'errors': 0,
        'test_details': [],
        'failures': [],
        'errors_list': [],
        'execution_time': None,
    }
    
    # Extract total tests
    total_match = re.search(r'Ran (\d+) test', output_text)
    if total_match:
        results['total_tests'] = int(total_match.group(1))
    
    # Extract execution time
    time_match = re.search(r'in ([\d.]+)s', output_text)
    if time_match:
        results['execution_time'] = float(time_match.group(1))
    
    # Extract test status - look for "ok" or "OK" at end of test lines
    results['passed'] = len(re.findall(r'\.\.\. (ok|OK)\s*$', output_text, re.MULTILINE))
    results['failed'] = len(re.findall(r'\.\.\. FAIL', output_text))
    results['errors'] = len(re.findall(r'\.\.\. ERROR', output_text))
    
    # Also check for "OK" at the end of test run
    if re.search(r'OK\s*$', output_text, re.MULTILINE) and results['failed'] == 0 and results['errors'] == 0:
        # All tests passed
        results['passed'] = results['total_tests']
    
    # Extract failure details
    failure_pattern = r'FAIL: ([\w.]+) \(([\w.]+)\)\n([^\n]+)\n([\s\S]*?)(?=\n\n|$)'
    for match in re.finditer(failure_pattern, output_text):
        test_name = match.group(1)
        test_class = match.group(2)
        test_desc = match.group(3).strip()
        error_details = match.group(4).strip()
        
        # Extract assertion error message
        assertion_match = re.search(r'AssertionError: (.+)', error_details)
        error_msg = assertion_match.group(1) if assertion_match else error_details[:200]
        
        results['failures'].append({
            'test_name': test_name,
            'test_class': test_class,
            'description': test_desc,
            'error': error_msg,
        })
    
    # Extract individual test results
    test_pattern = r'(test_\w+) \(([\w.]+)\)\n([^\n]+)\n\.\.\. (ok|FAIL|ERROR)'
    for match in re.finditer(test_pattern, output_text):
        test_name = match.group(1)
        test_class = match.group(2)
        description = match.group(3).strip()
        status = match.group(4)
        
        results['test_details'].append({
            'name': test_name,
            'class': test_class,
            'description': description,
            'status': status.upper(),
        })
    
    return results


def generate_report(results):
    """Generate a formatted evaluation report."""
    report = []
    report.append("=" * 70)
    report.append("MCC REGRESSION TEST SUITE - EVALUATION REPORT")
    report.append("=" * 70)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # Summary
    report.append("SUMMARY")
    report.append("-" * 70)
    report.append(f"Total Tests:     {results['total_tests']}")
    report.append(f"Passed:          {results['passed']} ✓")
    report.append(f"Failed:          {results['failed']} ✗")
    report.append(f"Errors:          {results['errors']} ✗")
    if results['execution_time']:
        report.append(f"Execution Time:  {results['execution_time']:.2f}s")
    report.append("")
    
    # Success rate
    if results['total_tests'] > 0:
        success_rate = (results['passed'] / results['total_tests']) * 100
        report.append(f"Success Rate:    {success_rate:.1f}%")
        report.append("")
    
    # Test details
    if results['test_details']:
        report.append("TEST DETAILS")
        report.append("-" * 70)
        for test in results['test_details']:
            status_symbol = "✓" if test['status'] == "OK" else "✗"
            report.append(f"{status_symbol} {test['name']}")
            report.append(f"  Class: {test['class']}")
            report.append(f"  Description: {test['description']}")
            report.append(f"  Status: {test['status']}")
            report.append("")
    
    # Failures
    if results['failures']:
        report.append("FAILURES")
        report.append("-" * 70)
        for i, failure in enumerate(results['failures'], 1):
            report.append(f"{i}. {failure['test_name']}")
            report.append(f"   Class: {failure['test_class']}")
            report.append(f"   Description: {failure['description']}")
            report.append(f"   Error: {failure['error']}")
            report.append("")
    
    # Overall status
    report.append("=" * 70)
    if results['failed'] == 0 and results['errors'] == 0:
        report.append("STATUS: ✓ ALL TESTS PASSED")
    else:
        report.append(f"STATUS: ✗ {results['failed']} TEST(S) FAILED, {results['errors']} ERROR(S)")
    report.append("=" * 70)
    
    return "\n".join(report)


def main():
    """Main function."""
    if len(sys.argv) > 1:
        # Read from file
        input_file = sys.argv[1]
        with open(input_file, 'r', encoding='utf-8') as f:
            output_text = f.read()
    else:
        # Read from stdin
        output_text = sys.stdin.read()
    
    # Parse results
    results = parse_test_output(output_text)
    
    # Generate report
    report = generate_report(results)
    
    # Output report
    print(report)
    
    # Save to file
    report_file = Path(__file__).parent / 'test_evaluation_report.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    # Save JSON results
    json_file = Path(__file__).parent / 'test_results.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nDetailed report saved to: {report_file}")
    print(f"JSON results saved to: {json_file}")
    
    # Exit with appropriate code
    sys.exit(0 if results['failed'] == 0 and results['errors'] == 0 else 1)


if __name__ == '__main__':
    main()

