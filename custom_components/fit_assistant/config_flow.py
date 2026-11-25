"""Admin creates a profile, then approves a short code displayed on the watch."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, MAX_ENTITIES, READ_DOMAINS, CONTROL_DOMAINS


def fields(options):
    return {
        vol.Optional('entities', default=list(options.get('entities', []))): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=list(READ_DOMAINS), multiple=True)),
        vol.Optional('controls', default=list(options.get('controls', []))): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=list(CONTROL_DOMAINS), multiple=True)),
    }


def validate(data):
    entities = list(dict.fromkeys(data.get('entities', [])))
    controls = list(dict.fromkeys(data.get('controls', [])))
    if len(set(entities + controls)) > MAX_ENTITIES:
        return None
    if any(x.partition('.')[0] not in READ_DOMAINS for x in entities):
        return None
    if any(x.partition('.')[0] not in CONTROL_DOMAINS for x in controls):
        return None
    return {'entities': entities, 'controls': controls}


class FitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            values = validate(user_input)
            name = user_input['name'].strip()
            if not name or len(name) > 40 or values is None:
                errors['base'] = 'invalid_profile'
            else:
                return self.async_create_entry(title=name, data={}, options=values)
        return self.async_show_form(step_id='user', data_schema=vol.Schema({
            vol.Required('name', default='Watch Fit 4'): str, **fields({})}), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return FitOptionsFlow()


class FitOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        old = dict(entry.options)
        errors = {}
        if user_input is not None:
            values = validate(user_input)
            code = user_input.get('pair_code', '').strip()
            revoke = user_input.get('revoke', False)
            if values is None:
                errors['base'] = 'invalid_profile'
            elif code and (revoke or old.get('token_hash')):
                errors['base'] = 'revoke_first'
            else:
                token_hash = old.get('token_hash')
                if revoke:
                    token_hash = None
                elif code:
                    token_hash = self.hass.data[DOMAIN]['pool'].consume(code)
                    if not token_hash:
                        errors['base'] = 'invalid_code'
                if not errors:
                    if token_hash:
                        values['token_hash'] = token_hash
                    return self.async_create_entry(title='', data=values)
        schema = fields(old)
        if old.get('token_hash'):
            schema[vol.Optional('revoke', default=False)] = bool
        else:
            schema[vol.Optional('pair_code')] = str
        return self.async_show_form(step_id='init', data_schema=vol.Schema(schema), errors=errors,
                                    description_placeholders={'status': 'Подключено' if old.get('token_hash') else 'Не подключено'})
