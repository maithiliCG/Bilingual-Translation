#!/usr/bin/env python3
"""
Automated test script for image handling fixes.

This script analyzes the backend logs to verify that all image handling
improvements are working correctly.

Usage:
    python test_image_handling.py [log_file]
    
    If no log file specified, uses backend/app.log
"""

import re
import sys
from pathlib import Path
from collections import defaultdict


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")


def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}❌ {text}{Colors.END}")


def test_adaptive_padding(logs):
    """Test 1: Verify adaptive padding is being used correctly"""
    print_header("Test 1: Adaptive Padding")
    
    # Find all adaptive padding logs
    pattern = r'Page (\d+): Using adaptive padding=(\d+) for box area=(\d+)'
    matches = re.findall(pattern, logs)
    
    if not matches:
        print_warning("No adaptive padding logs found. Did you process any documents?")
        return False
    
    errors = []
    padding_distribution = defaultdict(int)
    
    for page, padding, area in matches:
        padding = int(padding)
        area = int(area)
        padding_distribution[padding] += 1
        
        # Verify padding logic
        if area < 50000:
            expected = 12
        elif area < 200000:
            expected = 18
        else:
            expected = 25
        
        if padding != expected:
            errors.append(f"Page {page}: Expected padding {expected} for area {area}, got {padding}")
    
    if errors:
        print_error(f"Adaptive padding logic errors found:")
        for error in errors:
            print(f"  {error}")
        return False
    
    print_success(f"Adaptive padding working correctly ({len(matches)} images processed)")
    print(f"  Padding distribution:")
    for padding, count in sorted(padding_distribution.items()):
        size_label = "small" if padding == 12 else "medium" if padding == 18 else "large"
        print(f"    {padding} units ({size_label}): {count} images")
    
    return True


def test_yolo_matching(logs):
    """Test 2: Verify YOLO matching is working"""
    print_header("Test 2: YOLO Precision Upgrades")
    
    # Count YOLO upgrades
    yolo_upgrades = len(re.findall(r'YOLO precision upgrade', logs))
    
    # Count total crops
    total_crops = len(re.findall(r'Cropping region \[', logs))
    
    if total_crops == 0:
        print_warning("No crops found in logs")
        return False
    
    upgrade_rate = (yolo_upgrades / total_crops) * 100
    
    if upgrade_rate >= 50:
        print_success(f"YOLO upgrade rate: {upgrade_rate:.1f}% ({yolo_upgrades}/{total_crops})")
        print(f"  Target: ≥50% - EXCEEDED ✨")
    elif upgrade_rate >= 40:
        print_warning(f"YOLO upgrade rate: {upgrade_rate:.1f}% ({yolo_upgrades}/{total_crops})")
        print(f"  Target: ≥50% - Close but below target")
    else:
        print_error(f"YOLO upgrade rate: {upgrade_rate:.1f}% ({yolo_upgrades}/{total_crops})")
        print(f"  Target: ≥50% - Significantly below target")
        return False
    
    return True


def test_recovery_mechanism(logs):
    """Test 3: Verify recovery mechanism for lost crop tags"""
    print_header("Test 3: Crop Tag Recovery Mechanism")
    
    # Find recovery activations
    recovery_pattern = r'Page (\d+): (\d+) crop tag\(s\) lost during reconstruction'
    recovery_activations = re.findall(recovery_pattern, logs)
    
    # Find recovered tags
    recovered_tags = re.findall(r'Page (\d+): Recovering lost crop tag', logs)
    
    if not recovery_activations:
        print_success("No crop tags lost (recovery mechanism not needed)")
        return True
    
    total_lost = sum(int(count) for _, count in recovery_activations)
    total_recovered = len(recovered_tags)
    
    print_warning(f"Recovery mechanism activated {len(recovery_activations)} time(s)")
    print(f"  Total tags lost: {total_lost}")
    print(f"  Total tags recovered: {total_recovered}")
    
    if total_recovered >= total_lost:
        print_success("All lost tags successfully recovered")
        return True
    else:
        print_error(f"Some tags not recovered: {total_lost - total_recovered} still missing")
        return False


def test_fallback_mechanism(logs):
    """Test 4: Verify fallback cropping mechanism"""
    print_header("Test 4: Fallback Cropping Mechanism")
    
    # Find fallback attempts
    fallback_attempts = re.findall(r'Attempting fallback with expanded bounds', logs)
    fallback_successes = re.findall(r'Fallback crop successful', logs)
    
    if not fallback_attempts:
        print_success("No fallback needed (all crops succeeded on first try)")
        return True
    
    success_rate = (len(fallback_successes) / len(fallback_attempts)) * 100
    
    print_warning(f"Fallback mechanism activated {len(fallback_attempts)} time(s)")
    print(f"  Successful fallbacks: {len(fallback_successes)}")
    print(f"  Success rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print_success("Fallback mechanism working well")
        return True
    else:
        print_error("Fallback mechanism has low success rate")
        return False


def test_no_missing_images(logs):
    """Test 5: Verify no images are missing"""
    print_header("Test 5: Missing Images Check")
    
    # Extract expected vs actual crop counts per page
    pattern = r'Page (\d+): Gemini output has (\d+) crop refs, (\d+) unconverted markdown image tags \(expected: (\d+)\)'
    pages = re.findall(pattern, logs)
    
    if not pages:
        print_warning("No Gemini reconstruction logs found")
        return False
    
    missing_images = []
    total_images = 0
    
    for page, crop_refs, md_imgs, expected in pages:
        actual = int(crop_refs) + int(md_imgs)
        expected = int(expected)
        total_images += expected
        
        if actual < expected:
            missing_images.append((page, expected - actual, expected))
    
    if missing_images:
        print_error(f"Missing images detected on {len(missing_images)} page(s):")
        for page, count, expected in missing_images:
            print(f"  Page {page}: {count}/{expected} image(s) missing")
        return False
    else:
        print_success(f"No missing images ({len(pages)} pages, {total_images} images checked)")
        return True


def test_smart_trim(logs):
    """Test 6: Verify smart trim is working correctly"""
    print_header("Test 6: Smart Trim Analysis")
    
    # Find smart trim logs
    trim_pattern = r'Page (\d+): Smart trim removed ([\d.]+)% whitespace'
    keep_pattern = r'Page (\d+): Minimal whitespace \(([\d.]+)%\), keeping original'
    
    trimmed = re.findall(trim_pattern, logs)
    kept = re.findall(keep_pattern, logs)
    
    if not trimmed and not kept:
        print_warning("No smart trim logs found")
        return False
    
    print_success(f"Smart trim analysis:")
    print(f"  Images trimmed: {len(trimmed)}")
    print(f"  Images kept original: {len(kept)}")
    
    if trimmed:
        trim_percentages = [float(pct) for _, pct in trimmed]
        avg_trim = sum(trim_percentages) / len(trim_percentages)
        print(f"  Average whitespace removed: {avg_trim:.1f}%")
    
    return True


def test_coordinate_validation(logs):
    """Test 7: Check for coordinate validation issues"""
    print_header("Test 7: Coordinate Validation")
    
    # Find coordinate issues
    invalid_coords = re.findall(r'Invalid [xy] coords', logs)
    expanded_small = re.findall(r'Crop region too small.*expanding', logs)
    
    total_issues = len(invalid_coords) + len(expanded_small)
    
    if total_issues == 0:
        print_success("No coordinate validation issues found")
        return True
    
    print_warning(f"Coordinate issues detected (but handled):")
    if invalid_coords:
        print(f"  Invalid coordinates: {len(invalid_coords)} (auto-corrected)")
    if expanded_small:
        print(f"  Small crops expanded: {len(expanded_small)}")
    
    return True


def generate_summary(results):
    """Generate overall test summary"""
    print_header("Test Summary")
    
    passed = sum(results.values())
    total = len(results)
    pass_rate = (passed / total) * 100
    
    print(f"Tests passed: {passed}/{total} ({pass_rate:.1f}%)\n")
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {test_name}")
    
    print()
    
    if pass_rate == 100:
        print_success("All tests passed! Image handling fixes are working correctly. 🎉")
        return 0
    elif pass_rate >= 80:
        print_warning("Most tests passed, but some issues detected. Review warnings above.")
        return 1
    else:
        print_error("Multiple test failures detected. Review errors above.")
        return 2


def main():
    """Main test runner"""
    # Determine log file path
    if len(sys.argv) > 1:
        log_file = Path(sys.argv[1])
    else:
        log_file = Path(__file__).parent / "backend" / "app.log"
    
    if not log_file.exists():
        print_error(f"Log file not found: {log_file}")
        print(f"Usage: python {sys.argv[0]} [log_file]")
        return 1
    
    print(f"{Colors.BOLD}Reading logs from: {log_file}{Colors.END}")
    
    # Read log file
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = f.read()
    except Exception as e:
        print_error(f"Failed to read log file: {e}")
        return 1
    
    if not logs.strip():
        print_error("Log file is empty. Process some documents first.")
        return 1
    
    # Run all tests
    results = {
        "Adaptive Padding": test_adaptive_padding(logs),
        "YOLO Matching": test_yolo_matching(logs),
        "Recovery Mechanism": test_recovery_mechanism(logs),
        "Fallback Mechanism": test_fallback_mechanism(logs),
        "Missing Images": test_no_missing_images(logs),
        "Smart Trim": test_smart_trim(logs),
        "Coordinate Validation": test_coordinate_validation(logs),
    }
    
    # Generate summary
    return generate_summary(results)


if __name__ == "__main__":
    sys.exit(main())
