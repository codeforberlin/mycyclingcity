/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    Preferences.cpp
 * @author  Roland Rutz
 * @note    Mock Preferences implementation for native tests
 */

#ifdef UNITY_TEST_MODE

#include "Preferences.h"

// Global preferences instance (matching ESP32 API)
Preferences preferences;

#endif // UNITY_TEST_MODE
