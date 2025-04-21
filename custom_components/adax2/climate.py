import logging
import requests
import sanction  # Se till att detta finns med i manifestets requirements

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVAC_MODE_OFF,
    HVAC_MODE_HEAT,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.const import TEMP_CELSIUS

_LOGGER = logging.getLogger(__name__)

# Hjälpklass för API-kommunikation med Adax inklusive token-upphämtning
class AdaxAPI:
    def __init__(self, token=None, client_id=None, client_password=None):
        """
        Konstruerar API-klienten. Du kan antingen ange ett giltigt token direkt,
        eller så anger du client_id och client_password, och klienten hämtar token.
        """
        self._api_url = "https://api-1.adax.no/client-api"
        self._token = token
        self._client_id = client_id
        self._client_password = client_password
        if not self._token and self._client_id and self._client_password:
            self.refresh_token()

    def refresh_token(self):
        """Hämtar ett nytt token via Adax API med hjälp av client_id och client_password."""
        token_url = f"{self._api_url}/auth/token"
        try:
            client = sanction.Client(token_endpoint=token_url)
            client.request_token(grant_type="password", username=self._client_id, password=self._client_password)
            self._token = client.access_token
            _LOGGER.debug("Token erhållen: %s", self._token)
        except Exception as err:
            _LOGGER.error("Fel vid erhållande av token: %s", err)
            self._token = None

    def get_rooms(self):
        """Hämtar alla rum (Adax-element) från API:et."""
        # Om token saknas men klientuppgifter finns, försök hämta token
        if not self._token and self._client_id and self._client_password:
            self.refresh_token()

        if not self._token:
            _LOGGER.error("Inget giltigt token, kontrollera autentiseringsuppgifterna!")
            return []

        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            response = requests.get(f"{self._api_url}/rest/v1/content/", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("rooms", [])
        except Exception as err:
            _LOGGER.error("Fel vid hämtning av rum: %s", err)
            return []

    def set_temperature(self, room_id, temperature):
        """
        Sätter måltemperatur för ett specifikt rum.
        Förväntar sig att 'temperature' är i °C; omvandlar sedan till hundradelsgrader.
        """
        if not self._token and self._client_id and self._client_password:
            self.refresh_token()
        if not self._token:
            _LOGGER.error("Inget giltigt token, kontrollerna kan inte utföras!")
            return False

        headers = {"Authorization": f"Bearer {self._token}"}
        payload = {
            "rooms": [
                {
                    "id": room_id,
                    "targetTemperature": int(float(temperature) * 100)
                }
            ]
        }
        try:
            response = requests.post(f"{self._api_url}/rest/v1/control/", json=payload, headers=headers)
            response.raise_for_status()
            return True
        except Exception as err:
            _LOGGER.error("Fel vid ändring av temperatur för rum %s: %s", room_id, err)
            return False

# Klimatenhet för ett Adax-element
class AdaxClimate(ClimateEntity):
    def __init__(self, adax_api, room):
        """Initiera enheten med API-klienten och rumsdata."""
        self._api = adax_api
        self._room = room
        self._room_id = room.get("id")
        self._name = room.get("name", f"Adax Element {self._room_id}")
        self._current_temperature = None
        self._target_temperature = None
        self._hvac_mode = HVAC_MODE_HEAT

    @property
    def should_poll(self):
        """Meddela Home Assistant att enheten ska uppdateras automatiskt."""
        return True

    @property
    def name(self):
        return self._name

    @property
    def temperature_unit(self):
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        return self._current_temperature

    @property
    def target_temperature(self):
        return self._target_temperature

    @property
    def hvac_mode(self):
        return self._hvac_mode

    @property
    def hvac_modes(self):
        return [HVAC_MODE_OFF, HVAC_MODE_HEAT]

    @property
    def supported_features(self):
        return SUPPORT_TARGET_TEMPERATURE

    def set_temperature(self, **kwargs):
        """Kallas när användaren ändrar måltemperatur i HA."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return

        if self._api.set_temperature(self._room_id, temperature):
            self._target_temperature = temperature
            self.schedule_update_ha_state()

    def update(self):
        """
        Denna metod anropas periodiskt av Home Assistant.
        Här uppdateras enhetens status genom att hämta alla rum och filtrera fram detta rum.
        """
        rooms = self._api.get_rooms()
        for room in rooms:
            if room.get("id") == self._room_id:
                if "temperature" in room:
                    self._current_temperature = float(room.get("temperature", 0)) / 100.0
                if "targetTemperature" in room:
                    self._target_temperature = float(room.get("targetTemperature", 0)) / 100.0
                break

# Plattformuppsättning: skapar en eller flera enheter baserat på Adax API-svar
def setup_platform(hass, config, add_entities, discovery_info=None):
    """
    YAML-konfigurationsexempel:
    
    Ange antingen direkt ett token:
    
    climate:
      - platform: adax
        token: YOUR_GENERERADE_TOKEN
        
    Eller ange dina klientuppgifter så hämtas token automatiskt:
    
    climate:
      - platform: adax
        client_id: YOUR_CLIENT_ID
        client_password: YOUR_CLIENT_PASSWORD
        
    Om du vill begränsa skapandet till ett specifikt rum ange även room_id och (valfritt) ett namn:
    
    climate:
      - platform: adax
        client_id: YOUR_CLIENT_ID
        client_password: YOUR_CLIENT_PASSWORD
        room_id: 196341
        name: "Vardagsrum"
    """
    token = config.get("token")
    client_id = config.get("client_id")
    client_password = config.get("client_password")

    if not token and (not client_id or not client_password):
        _LOGGER.error("Ange antingen 'token' eller både 'client_id' och 'client_password' i konfigurationen!")
        return

    # Skapa API-klienten med antingen token eller klientuppgifter
    if token:
        adax_api = AdaxAPI(token=token)
    else:
        adax_api = AdaxAPI(client_id=client_id, client_password=client_password)

    room_id = config.get("room_id")
    entities = []

    if room_id:
        rooms = adax_api.get_rooms()
        room_found = None
        for room in rooms:
            if room.get("id") == room_id:
                room_found = room
                break
        if room_found:
            entities.append(AdaxClimate(adax_api, room_found))
        else:
            _LOGGER.error("Inget rum med id %s hittades!", room_id)
    else:
        # Auto-discovery: skapa en klimatenhet för varje Adax-element
        rooms = adax_api.get_rooms()
        for room in rooms:
            entities.append(AdaxClimate(adax_api, room))
        if not rooms:
            _LOGGER.error("Inga Adax-element hittades. Kontrollera dina autentiseringsuppgifter och API-status!")

    add_entities(entities)
