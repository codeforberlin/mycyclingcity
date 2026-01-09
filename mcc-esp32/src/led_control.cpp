#include "led_control.h"

static bool ledIsOn = false;
static unsigned long ledOnTime = 0;
static bool ledEnabled = false;

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
void setupLed(bool enabled) {
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
    ledEnabled = enabled;
}

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
void updateLed(bool pulseDetected) {
    if (!ledEnabled) return;

    if (pulseDetected) {
        ledIsOn = true;
        ledOnTime = millis();
        digitalWrite(LED_PIN, HIGH);
    }
    
    if (ledIsOn && millis() - ledOnTime >= 50) {
        ledIsOn = false;
        digitalWrite(LED_PIN, LOW);
    }
}