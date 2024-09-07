# pip install requests-toolbelt
# pip install prometheus_client
# pip install requests

import concurrent.futures
import logging
import time

import requests
from prometheus_client import start_http_server, Gauge, Counter, Summary
from requests.adapters import HTTPAdapter
from requests_toolbelt.adapters import source

# Configuration
# API_KEY = "0a7243c9-13f8-4959-aedf-69584fefda8c"
# AGENT_ID = "e895f776-e5e0-41f6-906f-aa45fe5dfc40"

API_KEY = "f388a0a8-13f1-44cc-b72d-eed08f6adffb"
AGENT_ID = "8513f528-11ad-430f-8f09-68aa5fe6ca4e"

topology = "{{ topology }}"
nid = int("{{ nid }}")

API_HEADERS = {
    "Accept": "*/*",
    "x-api-key": API_KEY,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

public_ip_gauge = Gauge('public_ip', 'Public IP address for each interface', ['local_ip', 'server_name', 'bind'])
ip_check_duration = Summary('ip_check_duration_seconds', 'Time taken to check public IP',
                            ['server_name', 'bind'])
successful_checks = Counter('successful_ip_checks_total', 'Total number of successful IP checks',
                            ['local_ip', 'server_name', 'bind'])
timeout_errors = Counter('ip_check_timeout_errors_total', 'Total number of timeout errors during IP checks',
                         ['local_ip', 'server_name', 'bind'])
other_errors = Counter('ip_check_other_errors_total', 'Total number of non-timeout errors during IP checks',
                       ['local_ip', 'server_name', 'bind'])


def format_virtual_address(instance_ord: int, location_ord: int, device_ord: int) -> str:
    return f"10.{instance_ord}.{location_ord}.{device_ord}"

def fetch_agent_instances() -> list:
    try:
        response = requests.get(
            f"https://api.proxcet.io/api/v1/agentInstance?agentId={AGENT_ID}",
            headers=API_HEADERS
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        logger.error(f"Failed to fetch agent instances: {error}")
        raise


def fetch_devices() -> list:
    try:
        response = requests.get(
            f"https://api.proxcet.io/api/v1/device?agentId={AGENT_ID}",
            headers=API_HEADERS
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        logger.error(f"Failed to fetch devices: {error}")
        raise


def fetch_bind_devices() -> list:
    devices = fetch_devices()

    if topology.lower() == "location":
        return [
            {
                "addr": device["bindTarget"],
                "server_name": device["location"]["name"],
                "bind": "local"
            }
            for device in devices if device["location"]["id"] == nid
        ]
    elif topology.lower() == "instance":
        instances = fetch_agent_instances()
        current_instance = next((instance for instance in instances if instance["id"] == nid), None)

        if not current_instance:
            raise ValueError(f"No agent instance found with ID {nid}")

        return [
            {
                "addr": format_virtual_address(current_instance["ordinal"], device["location"]["ordinal"],
                                               device["ordinal"]),
                "server_name": device["location"]["name"],
                "bind": current_instance["name"]
            }
            for device in devices
        ]
    else:
        raise ValueError(f"Unsupported topology: {topology}")


def execute_call(source_ip: str, server_name: str, bind: bool) -> str:
    with ip_check_duration.labels(server_name=server_name, bind=bind).time():
        with requests.Session() as session:
            # disable retries
            adapter = HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1)
            session.mount('https://', adapter)

            # use local address
            src = source.SourceAddressAdapter(source_ip)
            session.mount('https://', src)
            try:
                response = session.get('https://api.ipify.org/?format=text', timeout=5)
                public_ip = response.text.strip()
                logger.info(f"Successfully retrieved public IP for {source_ip}: {public_ip}")
                successful_checks.labels(local_ip=source_ip, server_name=server_name, bind=bind).inc()
                return public_ip
            except requests.Timeout:
                logger.error(f"Timeout error while getting public IP for {source_ip}")
                timeout_errors.labels(local_ip=source_ip, server_name=server_name, bind=bind).inc()
                return f"Timeout error for {source_ip}"
            except requests.RequestException as e:
                logger.error(f"Failed to get public IP for {source_ip}. Error: {str(e)}")
                other_errors.labels(local_ip=source_ip, server_name=server_name, bind=bind).inc()
                return f"Failed to get public IP for {source_ip}"


def main():
        start_http_server(7878)
        logger.info("Prometheus metrics server started on port 7878")
        devices = fetch_bind_devices()
        logger.info(f"Devices: {devices}")

        while True:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(execute_call, device['addr'], device["server_name"], device["bind"]): device
                    for device in
                    devices}

                for future in concurrent.futures.as_completed(futures):
                    device = futures[future]
                    public_ip = future.result()

                    if not public_ip.startswith("Failed") and not public_ip.startswith("Timeout"):
                        public_ip_gauge.labels(
                            local_ip=device['addr'],
                            server_name=device["server_name"],
                            bind=device["bind"]
                        ).set(hash(public_ip))

            time.sleep(8)


if __name__ == "__main__":
    main()
