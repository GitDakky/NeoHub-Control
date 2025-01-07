from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import requests
import json
from urllib.parse import urlencode

DEFAULT_URL = "https://neohub.co.uk/"
USER_LOGIN_ENDPOINT = "hm_user_login"
CACHE_VALUE_ENDPOINT = "hm_cache_value"
DEFAULT_CACHE_VALUE_REQUEST = "engineers,comfort,profile0,timeclock0,system,device_list,timeclock,live_info"

@dataclass
class Device:
    address: Optional[str] = None
    deviceid: Optional[str] = None
    devicename: Optional[str] = None
    hub_type: Optional[int] = None
    online: Optional[bool] = None
    type: Optional[str] = None
    version: Optional[int] = None
    share_name: Optional[str] = None
    share_id: Optional[str] = None
    tempformat: Optional[str] = None
    timezone: Optional[str] = None
    away: Optional[bool] = None
    holiday: Optional[bool] = None
    holidayend: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Device':
        # Filter out unknown fields
        known_fields = {k: v for k, v in data.items() if k in cls.__annotations__}
        return cls(**known_fields)

@dataclass
class LiveInfoDevice:
    HEAT_ON: Optional[bool] = False
    CURRENT_FLOOR_TEMPERATURE: Optional[float] = 0.0
    STANDBY: Optional[bool] = False
    MANUAL_OFF: Optional[bool] = False
    TIMER_ON: Optional[bool] = False
    WINDOW_OPEN: Optional[bool] = False
    AVAILABLE_MODES: List[str] = None
    WRITE_COUNT: Optional[int] = 0
    FLOOR_LIMIT: Optional[bool] = False
    DATE: Optional[str] = None
    HEAT_MODE: Optional[bool] = False
    OFFLINE: Optional[bool] = False
    HOLIDAY: Optional[bool] = False
    MODELOCK: Optional[bool] = False
    DEVICE_ID: Optional[int] = None
    RECENT_TEMPS: List[str] = None
    COOL_ON: Optional[bool] = False
    RELATIVE_HUMIDITY: Optional[int] = 0
    HOLD_COOL: Optional[float] = 0.0
    AWAY: Optional[bool] = False
    TIMECLOCK: Optional[bool] = False
    TEMPORARY_SET_FLAG: Optional[bool] = False
    PRG_TIMER: Optional[bool] = False
    LOCK: Optional[bool] = False
    MODULATION_LEVEL: Optional[int] = 0
    HC_MODE: Optional[str] = None
    SET_TEMP: Optional[str] = None
    LOW_BATTERY: Optional[bool] = False
    COOL_TEMP: Optional[float] = 0.0
    HOLD_ON: Optional[bool] = False
    HOLD_OFF: Optional[bool] = False
    ZONE_NAME: Optional[str] = None
    HOLD_TIME: Optional[str] = None
    COOL_MODE: Optional[bool] = False
    HOLD_TEMP: Optional[float] = 0.0
    PREHEAT_ACTIVE: Optional[bool] = False
    ACTIVE_PROFILE: Optional[int] = 0
    SWITCH_DELAY_LEFT: Optional[str] = None
    PIN_NUMBER: Optional[str] = None
    FAN_SPEED: Optional[str] = None
    ACTUAL_TEMP: Optional[str] = None
    TIME: Optional[str] = None
    ACTIVE_LEVEL: Optional[int] = 0
    FAN_CONTROL: Optional[str] = None
    PRG_TEMP: Optional[float] = 0.0
    THERMOSTAT: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.AVAILABLE_MODES is None:
            self.AVAILABLE_MODES = []
        if self.RECENT_TEMPS is None:
            self.RECENT_TEMPS = []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LiveInfoDevice':
        # Filter out unknown fields
        known_fields = {k: v for k, v in data.items() if k in cls.__annotations__}

        # Convert string values to appropriate types
        for field in ['CURRENT_FLOOR_TEMPERATURE', 'HOLD_COOL', 'COOL_TEMP', 'HOLD_TEMP', 'PRG_TEMP']:
            if field in known_fields and isinstance(known_fields[field], str):
                try:
                    known_fields[field] = float(known_fields[field])
                except (ValueError, TypeError):
                    known_fields[field] = 0.0

        # Ensure RECENT_TEMPS is a list
        if 'RECENT_TEMPS' in known_fields and isinstance(known_fields['RECENT_TEMPS'], str):
            known_fields['RECENT_TEMPS'] = [known_fields['RECENT_TEMPS']]
        elif 'RECENT_TEMPS' not in known_fields:
            known_fields['RECENT_TEMPS'] = []

        # Ensure AVAILABLE_MODES is a list
        if 'AVAILABLE_MODES' not in known_fields:
            known_fields['AVAILABLE_MODES'] = []

        return cls(**known_fields)

class NeoHub:
    def __init__(self, username: str, password: str, url: Optional[str] = None):
        self.username = username
        self.password = password
        self.url = url or DEFAULT_URL
        self.token = None
        self.session = requests.Session()

    def login(self) -> List[Device]:
        """Login to NeoHub and return list of devices."""
        params = {
            'USERNAME': self.username,
            'PASSWORD': self.password
        }
        
        response = self._form_post_request(USER_LOGIN_ENDPOINT, params)
        
        if response['STATUS'] != 1:
            raise Exception(f"Login failed with status: {response['STATUS']}")
        
        self.token = response['TOKEN']
        return [Device.from_dict(device) for device in response['devices']]

    def get_data(self, device_id: str) -> Dict[str, Any]:
        """Get detailed data for a specific device."""
        if not self.token:
            raise Exception("Not logged in. Call login() first")

        params = {
            'cache_value': DEFAULT_CACHE_VALUE_REQUEST,
            'device_id': device_id,
            'token': self.token
        }
        
        response = self._form_post_request(CACHE_VALUE_ENDPOINT, params)
        
        if response['STATUS'] not in [1, 201]:
            raise Exception(f"Unexpected status from getData: {response['STATUS']}")

        # Convert live info devices to proper objects
        if 'CACHE_VALUE' in response and 'live_info' in response['CACHE_VALUE']:
            devices = []
            for device_data in response['CACHE_VALUE']['live_info'].get('devices', []):
                try:
                    devices.append(LiveInfoDevice.from_dict(device_data))
                except Exception as e:
                    print(f"Warning: Failed to parse device data: {e}")
            response['CACHE_VALUE']['live_info']['devices'] = devices

        return response

    def set_temperature(self, device_id: str, zone_name: str, temperature: float) -> Dict[str, Any]:
        """Set target temperature for a specific zone."""
        if not self.token:
            raise Exception("Not logged in. Call login() first")

        params = {
            'device_id': device_id,
            'token': self.token,
            'zone': zone_name,
            'temperature': str(temperature)
        }
        
        response = self._form_post_request('hm_set_temp', params)
        if response['STATUS'] != 1:
            raise Exception(f"Failed to set temperature: {response.get('ERROR', 'Unknown error')}")
        return response

    def set_mode(self, device_id: str, zone_name: str, mode: str) -> Dict[str, Any]:
        """Set operation mode for a specific zone (HEAT/COOL/VENT)."""
        if not self.token:
            raise Exception("Not logged in. Call login() first")

        params = {
            'device_id': device_id,
            'token': self.token,
            'zone': zone_name,
            'mode': mode.upper()
        }
        
        response = self._form_post_request('hm_set_mode', params)
        if response['STATUS'] != 1:
            raise Exception(f"Failed to set mode: {response.get('ERROR', 'Unknown error')}")
        return response

    def set_away_mode(self, device_id: str, enabled: bool) -> Dict[str, Any]:
        """Enable or disable away mode for a device."""
        if not self.token:
            raise Exception("Not logged in. Call login() first")

        params = {
            'device_id': device_id,
            'token': self.token,
            'away': '1' if enabled else '0'
        }
        
        response = self._form_post_request('hm_set_away', params)
        if response['STATUS'] != 1:
            raise Exception(f"Failed to set away mode: {response.get('ERROR', 'Unknown error')}")
        return response

    def get_history(self, device_id: str, zone_name: str) -> Dict[str, Any]:
        """Get temperature history for a specific zone."""
        if not self.token:
            raise Exception("Not logged in. Call login() first")

        params = {
            'device_id': device_id,
            'token': self.token,
            'zone': zone_name
        }
        
        response = self._form_post_request('hm_get_history', params)
        if response['STATUS'] != 1:
            raise Exception(f"Failed to get history: {response.get('ERROR', 'Unknown error')}")
        return response

    def _form_post_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make a form POST request to the API."""
        url = f"{self.url}{endpoint}"
        response = self.session.post(url, data=params)
        response.raise_for_status()
        return response.json()
