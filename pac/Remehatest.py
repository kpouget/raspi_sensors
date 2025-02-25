#! /usr/bin/env python3

import base64
import hashlib
import json
import logging
import secrets
import urllib
import requests
import pathlib
import os
import yaml
import datetime
import json
import argparse
import time

class RemehaHomeAuthFailed(Exception):
    """Error to indicate that authentication failed."""

class RemehaHomeAPI:
    """Provide Remeha Home authentication tied to an OAuth2 based config entry."""

    def __init__(self):
        """Initialize Remeha Home auth."""
        self._session = requests.Session()

    def resolve_external_data(self, email, password) -> dict:
        """Resolve external data to tokens."""

        # Generate a random state and code challenge
        random_state = secrets.token_urlsafe()
        code_challenge = secrets.token_urlsafe(64)
        code_challenge_sha256 = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_challenge.encode("ascii")).digest()
            )
            .decode("ascii")
            .rstrip("=")
        )

        # Request the login page starting a new login transaction
        response = self._session.get(
            "https://remehalogin.bdrthermea.net/bdrb2cprod.onmicrosoft.com/oauth2/v2.0/authorize",
            params={
                "response_type": "code",
                "client_id": "6ce007c6-0628-419e-88f4-bee2e6418eec",
                "redirect_uri": "com.b2c.remehaapp://login-callback",
                "scope": "openid https://bdrb2cprod.onmicrosoft.com/iotdevice/user_impersonation offline_access",
                "state": random_state,
                "code_challenge": code_challenge_sha256,
                "code_challenge_method": "S256",
                "p": "B2C_1A_RPSignUpSignInNewRoomV3.1",
                "brand": "remeha",
                "lang": "en",
                "nonce": "defaultNonce",
                "prompt": "login",
                "signUp": "False",
            },
        )
        response.raise_for_status()

        # Find the request id from the headers and package it up in base64 encoded json
        request_id = response.headers["x-request-id"]
        state_properties_json = f'{{"TID":"{request_id}"}}'.encode("ascii")
        state_properties = (
            base64.urlsafe_b64encode(state_properties_json)
            .decode("ascii")
            .rstrip("=")
        )

        # Find the CSRF token in the "x-ms-cpim-csrf" header
        csrf_token = next(
            cookie.value
            for cookie in self._session.cookies
            if (
                cookie.name == "x-ms-cpim-csrf"
                and cookie.domain == ".remehalogin.bdrthermea.net"
            )
        )

        # Post the user credentials to authenticate
        response = self._session.post(
            "https://remehalogin.bdrthermea.net/bdrb2cprod.onmicrosoft.com/B2C_1A_RPSignUpSignInNewRoomv3.1/SelfAsserted",
            params={
                "tx": "StateProperties=" + state_properties,
                "p": "B2C_1A_RPSignUpSignInNewRoomv3.1",
            },
            headers={
                "x-csrf-token": csrf_token,
            },
            data={
                "request_type": "RESPONSE",
                "signInName": email,
                "password": password,
            },
        )
        response.raise_for_status()
        response_json = json.loads(response.text)

        if response_json["status"] != "200":
            raise RemehaHomeAuthFailed()

        # Request the authentication complete callback
        response = self._session.get(
            "https://remehalogin.bdrthermea.net/bdrb2cprod.onmicrosoft.com/B2C_1A_RPSignUpSignInNewRoomv3.1/api/CombinedSigninAndSignup/confirmed",
            params={
                "rememberMe": "false",
                "csrf_token": csrf_token,
                "tx": "StateProperties=" + state_properties,
                "p": "B2C_1A_RPSignUpSignInNewRoomv3.1",
            },
            allow_redirects=False,
        )
        response.raise_for_status()

        # Parse the callback url for the authorization code
        parsed_callback_url = urllib.parse.urlparse(response.headers["location"])
        query_string_dict = urllib.parse.parse_qs(parsed_callback_url.query)
        authorization_code = query_string_dict["code"]

        # Request a new token with the authorization code
        grant_params = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": "com.b2c.remehaapp://login-callback",
            "code_verifier": code_challenge,
            "client_id": "6ce007c6-0628-419e-88f4-bee2e6418eec",
        }
        return self._request_new_token(grant_params)

    def _request_new_token(self, grant_params):
        """Call the OAuth2 token endpoint with specific grant parameters."""
        with self._session.post(
            "https://remehalogin.bdrthermea.net/bdrb2cprod.onmicrosoft.com/oauth2/v2.0/token?p=B2C_1A_RPSignUpSignInNewRoomV3.1",
            data=grant_params,
            allow_redirects=True,
        ) as response:
            # NOTE: The OAuth2 token request sometimes returns a "400 Bad Request" response. The root cause of this
            #       problem has not been found, but this workaround allows you to reauthenticate at least. Otherwise
            #       Home Assistant would get stuck on refreshing the token forever.
            if response.status_code == 400:
                response_json = response.json()
                print(
                    "OAuth2 token request returned '400 Bad Request': %s",
                    response_json["error_description"],
                )

            response.raise_for_status()
            response_json = response.json()
            return response_json

    def cleanup(self):
        # Cleanup resources, close the session, etc.
        self._session.close()


def GetEnergy(access_token, appliance_id):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Ocp-Apim-Subscription-Key': 'df605c5470d846fc91e848b1cc653ddf'
    }

    jan_1st = datetime.datetime.now().replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    )
    today = datetime.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_of_today = today + datetime.timedelta(hours=23, minutes=59, seconds=59)

    jan_1st_string = jan_1st.strftime("%Y-%m-%d %H:%M:%S.%fZ")
    end_of_today_string = end_of_today.strftime("%Y-%m-%d %H:%M:%S.%fZ")

    resp = requests.get(
        'https://api.bdrthermea.net/Mobile/api'
        + f"/appliances/{appliance_id}/energyconsumption/yearly?"
        + f"startDate={jan_1st_string}&endDate={end_of_today_string}",
        headers=headers
    )

    return resp.json()


def GetTempValues(access_token):
    # Include your logic to request a new token here if needed

    # Example: Make a GET request using the obtained access token
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Ocp-Apim-Subscription-Key': 'df605c5470d846fc91e848b1cc653ddf'
    }

    try:
        response = requests.get(
            'https://api.bdrthermea.net/Mobile/api/homes/dashboard',
            headers=headers
        )
        response.raise_for_status()

        # Do something with the response if needed
        response_json = response.json()

        return response_json
    except Exception as e:
        print(f"Error making GET request: {e}")
        raise

def setTemperature(access_token):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Ocp-Apim-Subscription-Key': 'df605c5470d846fc91e848b1cc653ddf'
    }

    try:
        response = requests.get(
            'https://api.bdrthermea.net/Mobile/api/homes/dashboard',
            headers=headers
        )
        response.raise_for_status()

        # Do something with the response if needed
        response_json = response.json()
        climateZoneId = response_json["appliances"][0]["climateZones"][0]["climateZoneId"]
        zoneMode = response_json["appliances"][0]["climateZones"][0]["zoneMode"]
        valueSetpoint = response_json["appliances"][0]["climateZones"][0]["setPoint"]
        print(zoneMode)
        print(valueSetpoint)
    except Exception as e:
        print(f"Error making GET request: {e}")
        raise

    try:
        json_data = {'roomTemperatureSetPoint': 20}
        response = requests.post(
            f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climateZoneId}/modes/manual',
            headers=headers,
            json=json_data
        )
    except Exception as e:
        print(f"Error making POST request: {e}")
        raise

def setScheduleMode(access_token):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Ocp-Apim-Subscription-Key': 'df605c5470d846fc91e848b1cc653ddf'
    }

    try:
        response = requests.get(
            'https://api.bdrthermea.net/Mobile/api/homes/dashboard',
            headers=headers
        )
        response.raise_for_status()

        # Do something with the response if needed
        response_json = response.json()
        climateZoneId = response_json["appliances"][0]["climateZones"][0]["climateZoneId"]
        valueSetpoint = response_json["appliances"][0]["climateZones"][0]["setPoint"]
        zoneMode = response_json["appliances"][0]["climateZones"][0]["zoneMode"]
        print(zoneMode)
        print(valueSetpoint)

    except Exception as e:
        print(f"Error making GET request: {e}")
        raise

    try:
        json_data = {'heatingProgramId': 1}
        response = requests.post(
            f'https://api.bdrthermea.net/Mobile/api/climate-zones/{climateZoneId}/modes/schedule',
            headers=headers,
            json=json_data
        )
    except Exception as e:
        print(f"Error making POST request: {e}")
        raise


def connect(email, password):
    remeha_api = RemehaHomeAPI()
    result = remeha_api.resolve_external_data(email, password)
    return result.get('access_token')

###

from prometheus_client import start_http_server, Gauge, Histogram, generate_latest, CollectorRegistry
registry = CollectorRegistry()

WATER_PRESSURE = Gauge('pac_water_pressure','Water pressure', registry=registry)
TEMPERATURE = Gauge('temperature','Temperature measured (*C)', ["location"], registry=registry)
HEATER_STATE = Gauge('heater_state', 'Heater state', ["location"], registry=registry)
HEAT_DIFF = Gauge('heat_difference', 'Heat difference', ["location"], registry=registry)
HEAT_TARGET = Gauge('heat_target', 'Heat target', ["location"], registry=registry)

HEAT_CURRENT = Gauge('heat_current', 'Heat current', ["location"], registry=registry)
HEATER_ENERGY = Gauge('heater_energy', 'Heater energy', ["location", "type"], registry=registry)

GAS_CALORIFIC_VALUE = Gauge("gas_calorific_value", "Gas calorific value", registry=registry)

def update_prometheus(access_token, show):
    #setScheduleMode(access_token)
    dashboard_data = GetTempValues(access_token)

    data = dashboard_data["appliances"][0]

    gasCalorificValue = data["gasCalorificValue"]
    GAS_CALORIFIC_VALUE.set(gasCalorificValue)

    outdoorData = data["outdoorTemperatureInformation"]
    outdoorTemperature = outdoorData["applianceOutdoorTemperature"]
    TEMPERATURE.labels("pac_exterieur").set(outdoorTemperature)

    waterPressure = data["waterPressure"]
    WATER_PRESSURE.set(waterPressure)

    zone_data = data["climateZones"][0]
    if show:
        print(json.dumps(zone_data, indent=4))

    activeComfortDemand = zone_data["activeComfortDemand"]
    if activeComfortDemand == "Idle":
        HEATER_STATE.labels("pac_interieur").set(0)
    elif activeComfortDemand == "ProducingHeat":
        HEATER_STATE.labels("pac_interieur").set(1)
    else:
        HEATER_STATE.labels("pac_interieur").set(-1)

    roomTemperature = zone_data["roomTemperature"]
    TEMPERATURE.labels("pac_interieur").set(roomTemperature)
    HEAT_CURRENT.labels("pac_interieur").set(roomTemperature)

    roomTarget = zone_data["setPoint"]
    HEAT_TARGET.labels("pac_interieur").set(roomTarget)
    HEAT_DIFF.labels("pac_interieur").set(roomTemperature - roomTarget)

    appliance_id = data["applianceId"]

    energy_data = GetEnergy(access_token, appliance_id)
    if show:
        print(json.dumps(energy_data, indent=4))

    energyProductionTotal = energy_data["data"][0]["producerPerformanceStatistics"]["producers"][0]["energyProductionTotal"]
    HEATER_ENERGY.labels("pac_interieur", "production").set(energyProductionTotal)
    energyConsumptionTotal = energy_data["data"][0]["producerPerformanceStatistics"]["producers"][0]["energyConsumptionTotal"]
    HEATER_ENERGY.labels("pac_interieur", "consumption").set(energyConsumptionTotal)


def str_to_bool(value):
    if value.lower() in {'false', 'f', '0', 'no', 'n'}:
        return False
    elif value.lower() in {'true', 't', '1', 'yes', 'y'}:
        return True
    raise ValueError('{} is not a valid boolean value'.format(value))



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bind", metavar='ADDRESS', default='0.0.0.0', help="Specify alternate bind address [default: 0.0.0.0]")
    parser.add_argument("-p", "--port", metavar='PORT', default=8000, type=int, help="Specify alternate port [default: 8000]")
    parser.add_argument("-d", "--debug", metavar='DEBUG', type=str_to_bool, help="Turns on more verbose logging, showing sensor output and post responses [default: false]")
    parser.add_argument("-s", "--show", metavar='SHOW', type=str_to_bool, help="Show the data [default: false]")
    args = parser.parse_args()

    if args.debug:
        DEBUG = True

    THIS_DIR = pathlib.Path(os.path.realpath(__file__)).parent

    # Run the main function
    with open(THIS_DIR / ".env.yaml") as f:
        env = yaml.safe_load(f)

    first = True
    access_token = connect(env["email"], env["password"])
    while True:
        update_prometheus(access_token, args.show)

        if first and not args.show:
            # Start up the server to expose the metrics.
            start_http_server(addr=args.bind, port=args.port, registry=registry)
            logging.info("Listening on http://{}:{}".format(args.bind, args.port))
            first = False

        if args.show:
            print(generate_latest(registry).decode("ascii"))
            break

        time.sleep(60)
