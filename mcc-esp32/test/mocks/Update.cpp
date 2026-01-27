/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    Update.cpp
 * @author  Roland Rutz
 * @note    Mock Update implementation for native tests
 */

#ifdef UNITY_TEST_MODE

#include "Update.h"

// Global Update instance (matching ESP32 API)
UpdateClass Update;

#endif // UNITY_TEST_MODE
