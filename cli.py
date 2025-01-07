#!/usr/bin/env python3
import sys
import json
from neohub import NeoHub

def main():
    if len(sys.argv) < 3:
        print("Usage: python cli.py username password [device_name]")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    device_filter = sys.argv[3] if len(sys.argv) > 3 else None

    # Create NeoHub client
    client = NeoHub(username, password)

    try:
        # Login and get devices
        print("Logging in...")
        devices = client.login()
        print(f"Found {len(devices)} devices")

        # Filter devices if name provided
        if device_filter:
            devices = [d for d in devices if d.devicename == device_filter]
            if not devices:
                print(f"No device found with name: {device_filter}")
                sys.exit(1)

        # Process each device
        for device in devices:
            print(f"\nDevice: {device.devicename} (ID: {device.deviceid})")
            print(f"Type: {device.type}")
            print(f"Online: {device.online}")

            if device.online:
                # Get detailed data for online devices
                data = client.get_data(device.deviceid)
                
                # Print zone information
                for zone in data['CACHE_VALUE']['live_info']['devices']:
                    print(f"\nZone: {zone.ZONE_NAME}")
                    print(f"Current temperature: {zone.ACTUAL_TEMP}")
                    print(f"Target temperature: {zone.SET_TEMP}")
                    print(f"Heating: {'On' if zone.HEAT_ON else 'Off'}")
                    print(f"Mode: {zone.HC_MODE}")

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
