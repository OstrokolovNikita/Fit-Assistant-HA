"""Watch presentation only; permissions are enforced separately."""
THEMES = ("auto", "red", "orange", "yellow", "green", "blue", "violet", "pink", "graphite", "burgundy", "raspberry", "lavender", "teal", "amber", "cyan", "indigo", "mint")
BACKGROUNDS = THEMES
ICONS = ('auto', 'temp', 'humidity', 'light', 'chandelier', 'strip', 'power', 'socket', 'climate', 'cover', 'sensor', 'motion', 'door', 'battery')

def room_name(value):
    value = str(value or '').strip()
    return '' if value.casefold() in ('избранное', 'favorites') else value

def home_entity(options, ids):
    """Preserve existing pin; migrate legacy favorites once if no pin exists."""
    chosen = options.get('home_entity')
    if chosen in ids:
        return chosen
    cards = options.get('cards', {})
    return next((entity for entity in ids if cards.get(entity, {}).get('favorite') is True), None)


def decorate(items, options):
    pinned = home_entity(options, [item['id'] for item in items])
    cards = options.get('cards', {})
    result = []
    for index, original in enumerate(items):
        item = dict(original)
        area = item.pop('_area', '')
        cfg = cards.get(item['id'], {})
        item['name'] = cfg.get('label') or item['name']
        item['group'] = room_name(cfg.get('group')) or room_name(area) or 'Без комнаты'
        item['theme'] = cfg.get('theme') if cfg.get('theme') in THEMES else 'auto'
        item['background'] = cfg.get('background') if cfg.get('background') in BACKGROUNDS else 'auto'
        item['home'] = item['id'] == pinned
        item['favorite'] = item['home']
        item['icon'] = cfg.get('icon') if cfg.get('icon') in ICONS else 'auto'
        precision = cfg.get('precision', -1)
        if isinstance(precision, int) and 0 <= precision <= 3:
            item['precision'] = precision
        result.append((cfg.get('order', index + 1), index, item))
    return [item for _, _, item in sorted(result, key=lambda row: (row[0], row[1]))]
