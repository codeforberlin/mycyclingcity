/* Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * @file    rfid_mfrc522_control.cpp
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

#ifdef ENABLE_RFID

#include "rfid_mfrc522_control.h"
#include "led_control.h" // For the updateLed function


// --- Helper functions ---

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
String RFID_MFRC522_uidToHexString(byte *buffer, byte bufferSize) {
  String str = "";
  for (byte i = 0; i < bufferSize; i++) {
    if (buffer[i] < 0x10) {
      str += "0";
    }
    str += String(buffer[i], HEX);
  }
  return str;
}

/**
 * @brief Clears interrupt flags in MFRC522 register.
 * 
 * Writes 0x7F to the ComIrqReg register to clear all interrupt flags.
 * This is used to reset the interrupt state of the RFID reader.
 * 
 * @note Hardware interaction: MFRC522 RFID reader via SPI (register write)
 * @note Side effects: Modifies MFRC522 interrupt register
 */
void RFID_MFRC522_clearInt() {
  mfrc522.PCD_WriteRegister(mfrc522.ComIrqReg, 0x7F);
}

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
void RFID_MFRC522_setup() {
  SPI.begin();
  mfrc522.PCD_Init();
  
  if (debugEnabled) {
    Serial.print(F("MFRC522 Version: 0x"));
    Serial.println(mfrc522.PCD_ReadRegister(mfrc522.VersionReg), HEX);
  }

}

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
void RFID_MFRC522_loop_handler() {
    
    // Polling check for a new card
    if (mfrc522.PICC_IsNewCardPresent()) { 
        if (debugEnabled) Serial.println("RFID-MFRC522: New card detected (Polling).");

        if (mfrc522.PICC_ReadCardSerial()) { 
            
            String newIdTag = RFID_MFRC522_uidToHexString(mfrc522.uid.uidByte, mfrc522.uid.size);
            
            // IMPORTANT CHANGE: The UID of the detected card should replace the UserID (idTag).
            if (idTag != newIdTag) {
                idTag = newIdTag; // Assignment of RFID UID as current UserID
                if (debugEnabled) {
                    Serial.print(F("New UserID (idTag) set by RFID tag: "));
                    Serial.println(idTag);
                }
            } else {
                 if (debugEnabled) {
                    Serial.print(F("RFID tag read, UserID (idTag) is already: "));
                    Serial.println(idTag);
                }
            }
            
            if (ledEnabled) {
                // Let LED briefly light up on successful read
                updateLed(true); 
            }

            mfrc522.PICC_HaltA(); // Stop PICC
        } else {
             if (debugEnabled) Serial.println("RFID-MFRC522: Card detected, but read error.");
        }
    }
}

#endif // ENABLE_RFID