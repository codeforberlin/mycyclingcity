/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    velos.h
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 *
 * Velos calculation aligned with mcc-web/api/velos.py
 */

#ifndef VELOS_H
#define VELOS_H

#include <stddef.h>

static const int FKM_BASE_MM = 2300;
static const int VELOS_PER_KM = 100;

float calcFkmFactor(float radumfang_mm, float paedagogischer_bonus);
int calcVelosFromFkm(float km, float fkm_factor);
int calcVelos(float km, float radumfang_mm, float paedagogischer_bonus);
void formatVelosDE(int velos, char* buffer, size_t bufferSize);

#endif
