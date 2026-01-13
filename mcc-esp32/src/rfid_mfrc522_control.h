/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    rfid_mfrc522_control.h
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#ifndef RFID_MFRC522_CONTROL_H
#define RFID_MFRC522_CONTROL_H

#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>

// --- HARDWARE DEFINITIONEN ---
// Globale MFRC522 Instanz
extern MFRC522 mfrc522;

// --- Externe Projektvariablen ---
extern String idTag;
extern bool debugEnabled;
extern bool ledEnabled;

// --- FUNKTIONSPROTOTYPEN ---

/**
 * @brief Interrupt service routine for MFRC522 RFID reader (not currently implemented).
 * 
 * @note This function is declared but not implemented in the current codebase.
 */
void RFID_MFRC522_ISR();

/**
 * @brief Initializes the MFRC522 RFID reader module.
 * 
 * Initializes SPI communication and configures the MFRC522 RFID reader.
 * Reads and displays the chip version register for verification.
 * 
 * @note Hardware interaction: 
 *   - SPI bus (initialization)
 *   - MFRC522 RFID reader (SS_PIN, RST_PIN via SPI)
 * @note Side effects: Initializes SPI, configures MFRC522, writes to Serial
 */
void RFID_MFRC522_setup();

/**
 * @brief Main RFID polling handler called from main loop.
 * 
 * Polls the MFRC522 for new RFID cards. When a card is detected and read successfully,
 * converts the UID to hex string and updates the global idTag variable if it changed.
 * Triggers LED feedback if enabled.
 * 
 * This function uses polling instead of interrupts to detect cards.
 * 
 * @note Hardware interaction:
 *   - MFRC522 RFID reader (SPI communication for card detection and reading)
 *   - LED_PIN (via updateLed() if ledEnabled is true)
 * @note Side effects: Updates global idTag variable, controls LED, writes to Serial
 */
void RFID_MFRC522_loop_handler();

// --- Helper-Funktionen (Intern) ---
/**
 * @brief Converts RFID UID byte array to hexadecimal string representation.
 * 
 * Converts the raw UID bytes from MFRC522 into a lowercase hexadecimal string.
 * Each byte is represented as two hex characters (e.g., 0xAB becomes "ab").
 * 
 * @param buffer Pointer to byte array containing the UID
 * @param bufferSize Number of bytes in the buffer
 * @return String containing hexadecimal representation of UID (lowercase)
 * 
 * @note Pure logic function - string conversion only
 * @note Side effects: Allocates String object
 */
String RFID_MFRC522_uidToHexString(byte *buffer, byte bufferSize);

/**
 * @brief Clears interrupt flags in MFRC522 register.
 * 
 * Writes 0x7F to the ComIrqReg register to clear all interrupt flags.
 * This is used to reset the interrupt state of the RFID reader.
 * 
 * @note Hardware interaction: MFRC522 RFID reader via SPI (register write)
 * @note Side effects: Modifies MFRC522 interrupt register
 */
void RFID_MFRC522_clearInt();

/**
 * @brief Activates card reception mode on MFRC522 (not currently implemented).
 * 
 * @note This function is declared but not implemented in the current codebase.
 */
void RFID_MFRC522_activateRec();

#endif