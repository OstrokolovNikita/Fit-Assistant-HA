"""Admin creates a profile, then approves a short code displayed on the watch."""
from urllib.parse import urlsplit
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, MAX_ENTITIES, READ_DOMAINS, CONTROL_DOMAINS
from .layout import THEMES, ICONS, BACKGROUNDS, room_name, home_entity
from .trend import PERIODS
from .protocol import apply_pairing


def route_url(raw, external=False):
    """Only HTTP(S) origins supported by the watch, no credentials or URL paths."""
    raw = raw.strip()
    if not raw:
        return ''
    try:
        u = urlsplit(raw)
        host = u.hostname or ''
        port = u.port
        if (u.scheme not in (('https',) if external else ('http', 'https'))
                or not host or len(raw) > 240 or u.username is not None
                or u.password is not None or u.path not in ('', '/')
                or u.query or u.fragment or ':' in host or '..' in host
                or host[0] in '.-' or host[-1] in '.-'
                or any(ch not in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for ch in host)
                or (port is not None and port < 1)):
            return None
        return u.scheme + '://' + host + (':' + str(port) if port is not None else (':80' if u.scheme == 'http' else ''))
    except (ValueError, AttributeError):
        return None


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
            local = route_url(user_input.get('internal_url', old.get('internal_url', self.hass.config.internal_url or '')))
            external = route_url(user_input.get('external_url', old.get('external_url', self.hass.config.external_url or '')), True)
            if local is None or external is None:
                errors['base'] = 'invalid_address'
            elif values is None:
                errors['base'] = 'invalid_profile'
            elif code and revoke:
                errors['base'] = 'revoke_first'
            else:
                values = {**old, **values, 'internal_url': local, 'external_url': external}
                ids = selected(values)
                values['cards'] = {k:{key: value for key, value in v.items() if key != 'favorite'} for k,v in old.get('cards', {}).items() if k in ids}
                values['home_entity'] = user_input.get('home_entity', home_entity(old, ids))
                if values['home_entity'] not in ids:
                    values['home_entity'] = None
                values['keep_seconds'] = int(user_input.get('keep_seconds', old.get('keep_seconds', 15)))
                if values['keep_seconds'] not in (5, 10, 15, 30):
                    values['keep_seconds'] = 15
                values['language'] = user_input.get('language', old.get('language', 'en'))
                if values['language'] not in ('en', 'ru'):
                    values['language'] = 'en'
                pairing_error = apply_pairing(values, self.hass.data[DOMAIN]['pool'], code, revoke)
                if pairing_error:
                    errors['base'] = pairing_error
                if not errors:
                    # Pairing and revocation are committed immediately.
                    if user_input.get('edit_cards') and not code and not revoke and ids:
                        self._values = values
                        self._original = old
                        return await self.async_step_choose_card()
                    return self.async_create_entry(title='', data=values)
        schema = fields(old)
        ids = selected(old)
        choices = [{'value':'__none__', 'label':'None' if self.hass.config.language != 'ru' else 'Нет'}]
        for entity in ids:
            state = self.hass.states.get(entity)
            choices.append({'value':entity,'label':state.name if state else entity})
        schema[vol.Optional('home_entity', default=home_entity(old, ids) or '__none__')] = dropdown(choices)
        schema[vol.Optional('keep_seconds', default=str(old.get('keep_seconds',15) if old.get('keep_seconds',15) in (5,10,15,30) else 15))] = dropdown([{'value':str(n),'label':str(n)} for n in (5,10,15,30)])
        schema[vol.Optional('language', default=old.get('language','en') if old.get('language','en') in ('en','ru') else 'en')] = dropdown([{'value':'en','label':'English'}, {'value':'ru','label':'Русский'}])
        schema[vol.Optional('edit_cards', default=False)] = bool
        schema[vol.Optional('internal_url', default=old.get('internal_url', self.hass.config.internal_url or ''))] = str
        schema[vol.Optional('external_url', default=old.get('external_url', self.hass.config.external_url or ''))] = str
        schema[vol.Optional('pair_code')] = str
        if old.get('token_hash'):
            schema[vol.Optional('revoke', default=False)] = bool
        return self.async_show_form(step_id='init', data_schema=vol.Schema(schema), errors=errors,
                                    description_placeholders={'status': ('Подключено' if old.get('token_hash') else 'Не подключено') if self.hass.config.language == 'ru' else ('Connected' if old.get('token_hash') else 'Not connected')})


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
            group = room_name(user_input.get('group', ''))
            theme = user_input.get('theme', 'auto')
            background = user_input.get('background', 'auto')
            order = int(user_input.get('order', 1))
            icon = user_input.get('icon', 'auto')
            precision = int(user_input.get('precision', -1))
            history_hours = int(user_input.get('history_hours', 12))
            if len(label)>60 or len(group)>24 or theme not in THEMES or background not in BACKGROUNDS or icon not in ICONS or not -1<=precision<=3 or not 1<=order<=99 or history_hours not in PERIODS:
                errors['base'] = 'invalid_card'
            elif dict(self.config_entry.options) != self._original:
                return self.async_abort(reason='profile_changed')
            else:
                cards[entity] = {'label':label,'group':group,'theme':theme,'background':background,'order':order,'icon':icon,'precision':precision,'history_hours':history_hours}
                if user_input.get('another'):
                    return await self.async_step_choose_card()
                return self.async_create_entry(title='', data=self._values)
        themes = [{'value':k,'label':n} for k,n in zip(THEMES,(("Автоматически", "Красный", "Оранжевый", "Жёлтый", "Зелёный", "Синий", "Фиолетовый", "Розовый", "Графит", "Бургунди", "Малиновый", "Лавандовый", "Бирюзовый", "Янтарный", "Голубой", "Индиго", "Мятный") if self.hass.config.language == 'ru' else ("Automatic", "Red", "Orange", "Yellow", "Green", "Blue", "Violet", "Pink", "Graphite", "Burgundy", "Raspberry", "Lavender", "Teal", "Amber", "Cyan", "Indigo", "Mint")))]
        return self.async_show_form(step_id='card', data_schema=vol.Schema({
            vol.Optional('label', default=current.get('label','')): str,
            vol.Optional('group', default=room_name(current.get('group'))): str,
            vol.Required('theme', default=current.get('theme','auto')): dropdown(themes),
            vol.Required('background', default=current.get('background','auto')): dropdown([{'value':k,'label':n} for k,n in zip(BACKGROUNDS,(("Автоматически", "Красный", "Оранжевый", "Жёлтый", "Зелёный", "Синий", "Фиолетовый", "Розовый", "Графит", "Бургунди", "Малиновый", "Лавандовый", "Бирюзовый", "Янтарный", "Голубой", "Индиго", "Мятный") if self.hass.config.language == 'ru' else ("Automatic", "Red", "Orange", "Yellow", "Green", "Blue", "Violet", "Pink", "Graphite", "Burgundy", "Raspberry", "Lavender", "Teal", "Amber", "Cyan", "Indigo", "Mint")))]),
            vol.Required('order', default=current.get('order',selected(self._values).index(entity)+1)): selector.NumberSelector(selector.NumberSelectorConfig(min=1,max=99,step=1,mode=selector.NumberSelectorMode.BOX)),
            vol.Required('icon', default=current.get('icon','auto')): dropdown([{'value':k,'label':n} for k,n in zip(ICONS,(('Автоматически','Температура','Влажность','Лампочка','Люстра','Светодиодная лента','Выключатель','Розетка','Климат','Шторы','Датчик','Движение','Дверь','Батарея') if self.hass.config.language == 'ru' else ('Automatic','Temperature','Humidity','Bulb','Chandelier','LED strip','Switch','Socket','Climate','Cover','Sensor','Motion','Door','Battery')))]),
            vol.Required('precision', default=current.get('precision',-1)): selector.NumberSelector(selector.NumberSelectorConfig(min=-1,max=3,step=1,mode=selector.NumberSelectorMode.BOX)),
            vol.Required('history_hours', default=str(current.get('history_hours',12))): dropdown([{'value':str(h),'label':str(h) if h else ('Выключено' if self.hass.config.language == 'ru' else 'Off')} for h in PERIODS]),
            vol.Optional('another', default=False): bool,
        }), errors=errors, description_placeholders={'entity':entity})
