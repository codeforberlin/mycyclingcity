#
# Program: mcc_minecraft.py
# Copyright © MyCyclingCity
#
# Eine Brücke zwischen der MCC-Datenbank und dem Minecraft-Server.
# Verwaltet MQTT- und HTTP-Eingänge und übersetzt sie in Minecraft-RCON-Befehle.
#
# Changelog 2025-08-22:
# - Die Logik zur Erkennung von Minecraft-Spielern in der Mapping-Datei wurde korrigiert.
# - Es wird nun der neue Endpunkt '/get_mapped_minecraft_players' in mcc_db.py verwendet.
# - Der RCON-Worker-Thread wurde aktualisiert, um RCON-Befehle korrekt zu verarbeiten.

import json
import os
import configparser
import logging
import requests 
import time
import sys
import threading
import queue
import re
import argparse
from flask import Flask, request, jsonify
from mcrcon import MCRcon, MCRconException
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

rcon_connection = None

# Flask-App-Initialisierung
app = Flask(__name__)

# --- Konfiguration laden ---
config = configparser.ConfigParser()
CONFIG_FILE = "mcc_minecraft.conf"

if not os.path.exists(CONFIG_FILE):
    print(f"❌ Fehler: Konfigurationsdatei '{CONFIG_FILE}' nicht gefunden.")
    os._exit(1)

config.read(CONFIG_FILE)

# Lade globale Einstellungen
GENERAL_SETTINGS = config['general']
MCC_DB_SETTINGS = config['mcc_db']
MINECRAFT_SETTINGS = config['minecraft']
HTTP_SETTINGS = config['http']
FILES_SETTINGS = config['files']

UPDATE_INTERVAL = GENERAL_SETTINGS.getint('update_interval_seconds', 5)
MINECRAFT_GROUP_TYPE = GENERAL_SETTINGS.get('minecraft_group_type')
MINECRAFT_GROUP_NAME = GENERAL_SETTINGS.get('minecraft_group_name')
PLAYER_COINS_TOTAL = GENERAL_SETTINGS.get('player_coins_total')
PLAYER_COINS_SPENDABLE = GENERAL_SETTINGS.get('player_coins_spendable')
MCC_MINECRAFT_API_KEY = GENERAL_SETTINGS.get('mcc_minecraft_api_key')


# Minecraft RCON-Einstellungen
SERVER_IP = MINECRAFT_SETTINGS.get('server_host')
RCON_PASSWORD = MINECRAFT_SETTINGS.get('rcon_password')
SERVER_PORT = MINECRAFT_SETTINGS.getint('server_port')


# Thread-Safe-Warteschlange für RCON-Befehle
rcon_queue = queue.Queue()
executor = ThreadPoolExecutor(max_workers=1)

# --- Hilfsfunktionen ---
def run_rcon_command(command):
    """
    Führt einen RCON-Befehl in einem separaten Thread aus.
    Dies verhindert, dass der Hauptthread blockiert wird.
    """
    try:
        with MCRcon(SERVER_IP, RCON_PASSWORD, port=SERVER_PORT) as mcr:
            response = mcr.command(command)
            logging.info(f"RCON-Befehl '{command}' ausgeführt. Antwort: {response}")
            return response
    except MCRconException as e:
        logging.error(f"❌ RCON-Fehler beim Befehl '{command}': {e}")
        return None

def poll_rcon_queue():
    """
    Verarbeitet RCON-Befehle aus der Warteschlange im Haupt-Thread.
    """
    while not rcon_queue.empty():
        command = rcon_queue.get()
        if command is None:
            continue
        try:
            with MCRcon(SERVER_IP, RCON_PASSWORD, port=SERVER_PORT) as mcr:
                logging.info(f"📤 Sende RCON-Befehl: {command}")
                response = mcr.command(command)
                logging.info(f"✅ RCON-Antwort: {response}")
        except MCRconException as e:
            logging.error(f"❌ RCON-Fehler beim Senden des Befehls: {e}")
        except Exception as e:
            logging.error(f"❌ Unerwarteter Fehler beim Senden des Befehls: {e}")


def test_rcon_connection():
    """Stellt eine RCON-Verbindung her und testet sie."""
    try:
        logging.info("➡️ Versuche, mit dem Minecraft RCON-Server zu verbinden...")
        # Erstelle ein RCON-Objekt
        rcon_conn = MCRcon(SERVER_IP, RCON_PASSWORD, port=SERVER_PORT)
        rcon_conn.connect()
        logging.info("✅ Erfolgreich mit dem Minecraft RCON-Server verbunden.")
        return rcon_conn
    except Exception as e:
        logging.error(f"❌ Verbindung zum RCON-Server fehlgeschlagen: {e}")
        return None
           
# --- HTTP-Endpunkte ---
@app.route('/update-player-coins', methods=['POST'])
def update_player_coins():
    """
    HTTP-Endpunkt, um die Coins eines Spielers direkt in den Scoreboards im Server zu aktualisieren,
    der von der mcc_db.py aufgerufen wird.
    Fügt den Scoreboards immer den Wert der Coins hinzu (add) oder setzt den Wert neu (set)
    """
    api_key_header = request.headers.get('X-Api-Key')
    if api_key_header != MCC_MINECRAFT_API_KEY:
        logging.error("❌ Ungültiger API-Schlüssel für Minecraft-Bridge erhalten.")
        return jsonify({"error": "Ungültiger API-Schlüssel"}), 403

    data = request.get_json()
    username = data.get('username')
    coins = data.get('coins')
    action = data.get('action')

    if not all([username, coins is not None, action is not None]):
        return jsonify({"error": "Fehlende Daten"}), 400

    logging.info(f"✅ Erhalte Update für Spieler {username}: Coins={coins}, Action: {action}")

    # Füge RCON-Befehle zur Warteschlange hinzu oder zieht sie ab
    if action == "add":
      logging.info(f"PUT to RCON QUEUE: Update für Spieler {username}: Coins={coins}, Action: {action}")
      rcon_queue.put(f"scoreboard players add {username} {PLAYER_COINS_TOTAL} {int(coins)}")
      rcon_queue.put(f"scoreboard players add {username} {PLAYER_COINS_SPENDABLE} {int(coins)}")

    if action == "set":
      logging.info(f"PUT to RCON QUEUE: Update für Spieler {username}: Coins={coins}, Action: {action}")
      #rcon_queue.put(f"scoreboard players set {username} {PLAYER_COINS_TOTAL} {int(coins)}")
      rcon_queue.put(f"scoreboard players set {username} {PLAYER_COINS_SPENDABLE} {int(coins)}")


    return jsonify({"success": True})


# --- Polling-Funktion ---
def get_mapped_minecraft_players():
    """
    Ruft die Liste der gemappten Minecraft-Spieler vom mcc_db-Backend ab.
    """
    url = f"http://{MCC_DB_SETTINGS.get('db_host')}:{MCC_DB_SETTINGS.get('db_port')}/get_mapped_minecraft_players"
    api_key = MCC_DB_SETTINGS.get('mcc_db_api_key')
    headers = {'X-Api-Key': api_key}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Fehler beim Abrufen der Spielerliste von MCC-DB: {e}")
        return None

def poll_all_player_coins():
    """
    Fragt die Coins aller gemappten Spieler von der mcc_db ab und aktualisiert das Minecraft-Scoreboard.
    """
    while True:
        mapped_players = get_mapped_minecraft_players()
        if not mapped_players:
            logging.warning("⚠️ Keine Minecraft-Spieler in der Mapping-Datei gefunden. Überspringe Polling.")
            time.sleep(UPDATE_INTERVAL)
            continue

        
            
        for player_id, player_info in mapped_players.items():
            #logging.debug(f"Search for username in mapped_players")
            # Logge die gesamte player_info zur Fehlersuche
            logging.debug(f"Verarbeite Spieler mit ID: {player_id} und Info: {player_info}")

            username = player_info.get('mc_username')
            logging.debug(f"Got mc_username: {username}")

            if not username:
                continue

            try:
                url = f"http://{MCC_DB_SETTINGS.get('db_host')}:{MCC_DB_SETTINGS.get('db_port')}/get_player_coins/{username}"
                api_key = MCC_DB_SETTINGS.get('mcc_db_api_key')
                headers = {'X-Api-Key': api_key}
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                total_coins = data.get('coins_total', 0)
                spendable_coins = data.get('coins_spendable', 0)
                
                logging.debug(f"✅ Abruf erfolgreich für {username}: {total_coins} Coins insgesamt, {spendable_coins} ausgebbar.")

                # Füge RCON-Befehle zur Warteschlange hinzu
                rcon_queue.put(f"scoreboard players set {username} {PLAYER_COINS_TOTAL} {int(total_coins)}")
                rcon_queue.put(f"scoreboard players set {username} {PLAYER_COINS_SPENDABLE} {int(spendable_coins)}")

            except requests.exceptions.RequestException as e:
                logging.error(f"❌ Fehler beim Abrufen der Coins für Spieler {username} von MCC-DB: {e}")
            
        time.sleep(UPDATE_INTERVAL)


# --- HTTP-Server-Thread ---
def run_flask_app():
    """Startet die Flask-App."""
    app.run(host=HTTP_SETTINGS.get('host', '0.0.0.0'), 
            port=HTTP_SETTINGS.getint('port', 8080))


# --- Haupt-Logik ---
if __name__ == '__main__':

    # Füge diesen Block hinzu, um das Logging zu konfigurieren
    log_level = logging.DEBUG if GENERAL_SETTINGS.getboolean('debug_mode', False) else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    


    parser = argparse.ArgumentParser(description="MCC-Minecraft-Bridge")
    parser.add_argument("--test-ws", action="store_true", help="Testet nur die WebSocket-Verbindung und beendet sich dann.")
    parser.add_argument("--enable-http", action="store_true", help="Aktiviert den HTTP-Server.")
    
    args = parser.parse_args()

    # Verbinde im Haupt-Thread mit RCON
    rcon_connection = test_rcon_connection()
    if not rcon_connection:
        logging.error("❌ Kritischer Fehler: RCON-Verbindung konnte nicht hergestellt werden. Beende das Skript.")
        sys.exit(1)


    # Füge diese Zeilen hinzu, um die Scoreboards beim Start zu erstellen
    logging.info(f"Überprüfe und erstelle Scoreboards...")
    rcon_queue.put(f"scoreboard objectives add {PLAYER_COINS_TOTAL} dummy \"Gesamt-Coins\"")
    rcon_queue.put(f"scoreboard objectives add {PLAYER_COINS_SPENDABLE} dummy \"Ausgebbare Coins\"")
    #RR TODO: bei Bedarf ein weiteres Scoreboard mit distance_total befüllen



    # Hier können RCON-Befehle ausgelöst werden, z.B. für eine In-Game-Nachricht oder ein Scoreboard-Update
    #rcon_queue.put(f"tellraw @a [\"\",{{\"text\":\"Spieler {username} hat {coins_spent} Coins ausgegeben!\"}}]")


    # Starte den HTTP-Server-Thread, falls aktiviert
    if args.enable_http:
        logging.info("Starte HTTP-Server...")
        http_thread = threading.Thread(target=run_flask_app)
        http_thread.daemon = True
        http_thread.start()
        
    # Starte den Polling-Thread
    logging.info("Starte periodische Datenbank-Abfrage...")
    polling_thread = threading.Thread(target=poll_all_player_coins)
    polling_thread.daemon = True
    polling_thread.start()

    # Die Endlosschleife, die das Hauptprogramm am Laufen hält und die RCON-Warteschlange verarbeitet
    try:
        while True:
            poll_rcon_queue() # NEUE FUNKTION HIER AUFRUFEN
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Server heruntergefahren.")
        rcon_queue.put(None)
        sys.exit(0)
