"""Watch card presentation; never changes authorization."""
THEMES = ('auto', 'blue', 'teal', 'amber', 'violet', 'red')
ICONS = ('auto', 'temp', 'humidity', 'light', 'power', 'climate', 'cover', 'sensor')

def decorate(items, options):
    cards = options.get('cards', {})
    result = []
    for index, original in enumerate(items):
        item = dict(original)
        cfg = cards.get(item['id'], {})
        item['name'] = cfg.get('label') or item['name']
        item['group'] = cfg.get('group') or 'Избранное'
        item['theme'] = cfg.get('theme') if cfg.get('theme') in THEMES else 'auto'
        item['favorite'] = bool(cfg.get('favorite', item['group'] == 'Избранное'))
        item['icon'] = cfg.get('icon') if cfg.get('icon') in ICONS else 'auto'
        precision = cfg.get('precision', -1)
        if isinstance(precision, int) and 0 <= precision <= 3:
            item['precision'] = precision
        result.append((cfg.get('order', index + 1), index, item))
    return [item for _, _, item in sorted(result, key=lambda row: (row[0], row[1]))]
