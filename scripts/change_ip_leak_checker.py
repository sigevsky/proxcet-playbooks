# nohup python3 check-ip.py > change_ip.log 2>&1 &
import threading
from datetime import datetime, timezone
import requests
import subprocess
import time
import json
import logging

providers = {
    'ipinfo': 'ipinfo.io/ip',
    'ipify': 'https://api.ipify.org/?format=text'
}

# Set up logging
logging.basicConfig(filename='change_ip.log', level=logging.INFO, format='%(asctime)s %(message)s')

logging.info('Starting')


# Function to execute the curl command and get the IP address
def get_ip(provider: str):
    try:
        result = subprocess.run(
            ['curl', '-x', 'socks5://R4PvPTD6:NpA623am@helsinki-gw.soxies.app:1080', provider],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing curl command: {e}")
        return None


# Function to change IP and get the response from the API
def change_ip():
    try:
        response = requests.get('https://api.proxcet.io/api/v1/change-ip?uuid=rdyHtts6')
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Error changing IP: {response.status_code}, {response}")
            return None
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None


def background_ip_check():
    while True:
        current_ip = get_ip(providers['ipify'])
        if current_ip:
            print(f"Background check - Current IP: {current_ip}")
        else:
            print("Background check - Error: Failed to get current IP.")
        time.sleep(0.1)


# Start the background IP checking thread
background_thread = threading.Thread(target=background_ip_check, daemon=True)
background_thread.start()

# Main loop to perform the actions at intervals
while True:
    ct = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    current_ip = get_ip(providers['ipinfo'])
    if current_ip:
        start_time = time.time()
        ip_info = change_ip()
        end_time = time.time()
        if ip_info and 'oldIp' in ip_info and 'newIp' in ip_info:
            old_ip = ip_info['oldIp']
            new_ip = ip_info['newIp']
            if current_ip == old_ip and old_ip != new_ip:
                duration = end_time - start_time
                logging.info(f"Old IP: {old_ip}, New IP: {new_ip}, Time taken to change IP: {duration:.2f} seconds")
            else:
                logging.error(f"Error: IP mismatch or new IP is the same as old IP. Current IP: {current_ip}, Response: {ip_info}")
        else:
            logging.error(f"Error: Invalid response from IP change API")
    else:
        logging.error("Error: Failed to get current IP.")

    time.sleep(60)