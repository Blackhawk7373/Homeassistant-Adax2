"""Adax integration for Home Assistant."""
DOMAIN = "adax2"

def setup(hass, config):
    """Legacy setup; om du inte implementerar config_flow."""
    hass.data[DOMAIN] = {}
    return True
