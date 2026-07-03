/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    velos.cpp
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#include "velos.h"

#include <cmath>
#include <cstdio>
#include <cstring>

float calcFkmFactor(float radumfang_mm, float paedagogischer_bonus) {
    if (radumfang_mm <= 0.0f) {
        return 1.0f;
    }
    return (static_cast<float>(FKM_BASE_MM) / radumfang_mm) + paedagogischer_bonus;
}

int calcVelosFromFkm(float km, float fkm_factor) {
    return static_cast<int>(km * static_cast<float>(VELOS_PER_KM) * fkm_factor);
}

int calcVelos(float km, float radumfang_mm, float paedagogischer_bonus) {
    return calcVelosFromFkm(km, calcFkmFactor(radumfang_mm, paedagogischer_bonus));
}

void formatVelosDE(int velos, char* buffer, size_t bufferSize) {
    if (buffer == nullptr || bufferSize == 0) {
        return;
    }

    char digits[16];
    snprintf(digits, sizeof(digits), "%d", velos);
    const size_t len = strlen(digits);
    if (len == 0) {
        buffer[0] = '\0';
        return;
    }

    const size_t firstGroup = (len % 3 == 0) ? 3 : (len % 3);
    size_t out = 0;

    for (size_t i = 0; i < len; ++i) {
        if (i == firstGroup || (i > firstGroup && (i - firstGroup) % 3 == 0)) {
            if (out + 2 >= bufferSize) {
                break;
            }
            buffer[out++] = '.';
        }
        if (out + 1 >= bufferSize) {
            break;
        }
        buffer[out++] = digits[i];
    }

    buffer[out] = '\0';
}
