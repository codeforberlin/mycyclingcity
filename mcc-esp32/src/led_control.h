/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    led_control.h
 * @author  Roland Rutz
 */

#ifndef LED_CONTROL_H
#define LED_CONTROL_H

#include <Arduino.h>

/**
 * @brief Initializes the LED pin and enables/disables LED functionality.
 * 
 * Configures LED_PIN as output and sets initial state to LOW (off).
 * Stores the enabled state for use by updateLed().
 * 
 * @param enabled If true, LED will respond to pulse events; if false, LED remains off
 * 
 * @note Hardware interaction: LED_PIN (GPIO output configuration)
 * @note Side effects: Configures GPIO pin, sets LED state
 */
void setupLed(bool enabled);

/**
 * @brief Updates LED state based on pulse detection.
 * 
 * If LED is enabled and a pulse is detected, turns LED on for 50ms.
 * Automatically turns LED off after the timeout period.
 * 
 * @param pulseDetected If true, triggers LED to turn on for 50ms
 * 
 * @note Hardware interaction: LED_PIN (GPIO output)
 * @note Side effects: Controls LED state based on pulse events
 */
void updateLed(bool pulseDetected);

#endif