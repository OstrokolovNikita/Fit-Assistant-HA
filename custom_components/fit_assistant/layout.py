"""Watch presentation only; permissions are enforced separately."""
THEMES = ('auto', 'blue', 'teal', 'amber', 'violet', 'red')
BACKGROUNDS = ('auto', 'graphite', 'blue', 'teal', 'amber', 'violet', 'red')
ICONS = ('auto', 'temp', 'humidity', 'light', 'chandelier', 'strip', 'power', 'socket', 'climate', 'cover', 'sensor', 'motion', 'door', 'battery')

def room_name(value):
    value = str(value or '').strip()
    return '' if value.casefold() in ('избранное', 'favorites') else value

def decorate(items, options):
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
        item['favorite'] = cfg.get('favorite') is True
        item['icon'] = cfg.get('icon') if cfg.get('icon') in ICONS else 'auto'
        precision = cfg.get('precision', -1)
        if isinstance(precision, int) and 0 <= precision <= 3:
            item['precision'] = precision
        result.append((cfg.get('order', index + 1), index, item))
    return [item for _, _, item in sorted(result, key=lambda row: (row[0], row[1]))]
