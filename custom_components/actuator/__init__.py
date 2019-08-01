
import datetime
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_call_later

import logging
_LOGGER = logging.getLogger(__name__)


DOMAIN = 'actuator'

ACTUATE_SCHEMA = vol.Schema({
    vol.Required('sensor_id'): cv.string,
    vol.Optional('sensor_attr'): cv.string,
    vol.Required('sensor_values'): list,
    vol.Optional('alt_sensor_values'): list,
    vol.Optional('alt_time_range'): list,
    vol.Required('entity_id'): cv.string,
    vol.Optional('entity_attr'): cv.string,
    vol.Optional('service'): cv.string,
    vol.Optional('service_attr'): cv.string,
    vol.Required('entity_values'): list,
    vol.Optional('delay'): int,
})

_hass = None
_executors = {}

def execute(params):
    sensor_id = params.get('sensor_id')
    sensor_attr = params.get('sensor_attr')
    alt_time_range = params.get('alt_time_range') or [20, 8]

    hour = datetime.datetime.now().hour
    if alt_time_range[1] > alt_time_range[0]:
        alt_time = hour > alt_time_range[0] and hour < alt_time_range[1]
    else:
        alt_time = hour > alt_time_range[0] or hour < alt_time_range[1]
    sensor_values = params.get('alt_sensor_values' if alt_time and 'alt_sensor_values' in params else 'sensor_values')

    sensor_state = _hass.states.get(sensor_id)
    try:
        sensor_attributes = sensor_state.attributes
        sensor_value = float(sensor_state.state if sensor_attr is None else sensor_attributes.get(sensor_attr))
    except AttributeError:
        _LOGGER.error("Sensor %s %s error", sensor_id, sensor_attr or '')
        return

    sensor_log = sensor_attributes.get('friendly_name')
    if sensor_attr:
         sensor_log += '.' + sensor_attr
    sensor_log += '=' + str(sensor_value)

    entity_id = params.get('entity_id')
    entity_attr = params.get('entity_attr')
    service_attr = params.get('service_attr') or entity_attr
    service = params.get('service') or 'set_' + service_attr
    entity_values = params.get('entity_values')
    domain = entity_id[:entity_id.find('.')]

    state = _hass.states.get(entity_id)
    if state is None:
        _LOGGER.error("Entity %s error", sensor_id)
        return
    state_value = state.state
    state_attributes = state.attributes
    entity_log = state_attributes.get('friendly_name')

    i = len(sensor_values) - 1
    while i >= 0:
        if sensor_value >= sensor_values[i]:
            from_value = state_value if entity_attr is None else state_attributes.get(entity_attr)
            to_value = entity_values[i]

            if entity_attr:
                entity_log += '.' + entity_attr
            entity_log += '=' + str(from_value)

            if state_value == 'off':
                entity_log += ', ->on'
                _hass.services.call(domain, 'turn_on', {'entity_id': entity_id}, True)

            if from_value == to_value:
                _LOGGER.debug('%s; %s', sensor_log, entity_log)
                return

            data = {'entity_id': entity_id, service_attr or entity_attr: to_value}
            _LOGGER.warn('%s; %s, %s=>%s', sensor_log, entity_log, service, to_value)
            _hass.services.call(domain, service, data, True)
            return
        else:
            i = i - 1

    if state_value == 'off':
        _LOGGER.debug('%s, %s=off', sensor_log, entity_log)
        return

    _LOGGER.warn('%s, %s=%s, ->off', sensor_log, entity_log, state_value)
    _hass.services.call(domain, 'turn_off', {'entity_id': entity_id}, True)

class DelayExecutor(object):
    
    def __init__(self, key, delay, params):
        self.key = key
        self.params = params
        async_call_later(_hass, delay, self.call)

    def call(self, *_):
        execute(self.params)
        del _executors[self.key]

def actuate(call):
    params = call.data
    delay = params.get('delay')
    if delay is None:
        delay = 180
    if delay == 0:
        execute(params)
    else:
        key = params['entity_id'] + '~' +(params.get('service_attr') or params.get('entity_attr'))
        if key not in _executors:
            _executors[key] = DelayExecutor(key, delay, params)
        #else:
        #    _LOGGER.debug('%s ignored', key)

def setup(hass, config):
    global _hass
    _hass = hass
    hass.services.register(DOMAIN, 'actuate', actuate, schema=ACTUATE_SCHEMA)
    return True