/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    test_velos.cpp
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#include <unity.h>
#include <cstring>

#include "../src/velos.h"
#include "../src/velos.cpp"

static const float PAEDAGOGICAL_BONUS = 0.3f;

void test_velos() {
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 1.0f, calcFkmFactor(2300.0f, 0.0f));
    TEST_ASSERT_FLOAT_WITHIN(
        0.0001f,
        static_cast<float>(FKM_BASE_MM) / 1600.0f + PAEDAGOGICAL_BONUS,
        calcFkmFactor(1600.0f, PAEDAGOGICAL_BONUS)
    );

    TEST_ASSERT_EQUAL_INT(100, calcVelosFromFkm(1.0f, 1.0f));
    TEST_ASSERT_EQUAL_INT(0, calcVelosFromFkm(0.005f, 1.0f));
    TEST_ASSERT_EQUAL_INT(1, calcVelosFromFkm(0.015f, 1.0f));

    TEST_ASSERT_EQUAL_INT(100, calcVelos(1.0f, 2300.0f, 0.0f));

    const int velos29 = calcVelos(1.0f, 2300.0f, 0.0f);
    const int velos20 = calcVelos(1.0f, 1600.0f, PAEDAGOGICAL_BONUS);
    TEST_ASSERT_TRUE(velos20 > velos29);

    char formatted[16];
    formatVelosDE(0, formatted, sizeof(formatted));
    TEST_ASSERT_EQUAL_STRING("0", formatted);

    formatVelosDE(4520, formatted, sizeof(formatted));
    TEST_ASSERT_EQUAL_STRING("4.520", formatted);

    formatVelosDE(100, formatted, sizeof(formatted));
    TEST_ASSERT_EQUAL_STRING("100", formatted);

    formatVelosDE(1000, formatted, sizeof(formatted));
    TEST_ASSERT_EQUAL_STRING("1.000", formatted);
}
