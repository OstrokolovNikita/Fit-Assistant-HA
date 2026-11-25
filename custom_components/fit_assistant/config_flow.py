"""Admin creates a profile, then approves a short code displayed on the watch."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, MAX_ENTITIES, READ_DOMAINS, CONTROL_DOMAINS
from .layout import THEMES


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


def selected(options):
    return list(dict.fromkeys(options.get('entities', []) + options.get('controls', [])))


def dropdown(options):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN))


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
                ids = selected(values)
                values['cards'] = {k:v for k,v in old.get('cards', {}).items() if k in ids}
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
                    # Pairing and revocation are committed immediately.
                    if user_input.get('edit_cards') and not code and not revoke and ids:
                        self._values = values
                        self._original = old
                        return await self.async_step_choose_card()
                    return self.async_create_entry(title='', data=values)
        schema = fields(old)
        schema[vol.Optional('edit_cards', default=False)] = bool
        if old.get('token_hash'):
            schema[vol.Optional('revoke', default=False)] = bool
        else:
            schema[vol.Optional('pair_code')] = str
        return self.async_show_form(step_id='init', data_schema=vol.Schema(schema), errors=errors,
                                    description_placeholders={'status': 'Подключено' if old.get('token_hash') else 'Не подключено'})


    async def async_step_choose_card(self, user_input=None):
        ids = selected(self._values)
        if user_input and user_input.get('entity') in ids:
            self._entity = user_input['entity']
            return await self.async_step_card()
        choices = []
        for entity in ids:
            state = self.hass.states.get(entity)
            name = state.name if state else entity
            choices.append({'value':entity, 'label':f'{name} ({entity})'})
        return self.async_show_form(step_id='choose_card', data_schema=vol.Schema({
            vol.Required('entity'): dropdown(choices)}))

    async def async_step_card(self, user_input=None):
        entity = self._entity
        cards = self._values['cards']
        current = cards.get(entity, {})
        errors = {}
        if user_input is not None:
            label = user_input.get('label', '').strip()
            group = user_input.get('group', '').strip() or 'Избранное'
            theme = user_input.get('theme', 'auto')
            order = int(user_input.get('order', 1))
            if len(label)>60 or len(group)>24 or theme not in THEMES or not 1<=order<=99:
                errors['base'] = 'invalid_card'
            elif dict(self.config_entry.options) != self._original:
                return self.async_abort(reason='profile_changed')
            else:
                cards[entity] = {'label':label,'group':group,'theme':theme,'order':order}
                if user_input.get('another'):
                    return await self.async_step_choose_card()
                return self.async_create_entry(title='', data=self._values)
        themes = [{'value':k,'label':n} for k,n in zip(THEMES,('Автоматически','Синий','Бирюзовый','Янтарный','Фиолетовый','Красный'))]
        return self.async_show_form(step_id='card', data_schema=vol.Schema({
            vol.Optional('label', default=current.get('label','')): str,
            vol.Optional('group', default=current.get('group','Избранное')): str,
            vol.Required('theme', default=current.get('theme','auto')): dropdown(themes),
            vol.Required('order', default=current.get('order',selected(self._values).index(entity)+1)): selector.NumberSelector(selector.NumberSelectorConfig(min=1,max=99,step=1,mode=selector.NumberSelectorMode.BOX)),
            vol.Optional('another', default=False): bool,
        }), errors=errors, description_placeholders={'entity':entity})
