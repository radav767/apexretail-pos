"""Fixed layout vocabulary; only escaped text, frozen source and validated PNG."""
from .documents import text

def render_layout(template,snapshot):
    paper=template['paper'];width={'58mm':'58mm','80mm':'80mm','A4':'210mm'}[paper]
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
        '<title>'+text(snapshot['title'])+'</title><style>body{font:12px system-ui;color:#111;background:white;max-width:'+width+';margin:4mm auto;padding:2mm}table{width:100%;table-layout:fixed;border-collapse:collapse}td,th{padding:1mm;overflow-wrap:anywhere;text-align:left;border-bottom:1px solid #ccc}p{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%;height:auto}@page{margin:4mm}</style></head><body><main>',
        '<h1>'+text(snapshot['title'])+'</h1><p>'+text(snapshot['identity'])+'</p><p>'+text(snapshot['notice'])+'</p>']
    def items():
        parts.append('<table><caption>Recorded items and quantities</caption><thead><tr><th scope="col">Item / position</th><th scope="col">Quantity</th><th scope="col">Amount / review</th></tr></thead><tbody>')
        for row in snapshot['rows']:parts.append('<tr><td>'+text(row['name'])+'</td><td>'+text(row.get('quantity'))+'</td><td>'+text(row.get('amount'))+'</td></tr>')
        parts.append('</tbody></table>')
    def totals():
        for label,value in snapshot.get('totals',{}).items():parts.append('<p>'+text(label)+': '+text(value)+'</p>')
    placed=set()
    for block in template['blocks']:
        kind=block['kind']
        if kind=='logo':
            asset=template['media'][block['media_id']]
            parts.append('<div style="text-align:'+block['alignment']+'"><img alt="Business supplied logo" width="'+str(round(block['width_mm']*96/25.4))+'" style="height:30mm;object-fit:contain" src="data:image/png;base64,'+asset['data_base64']+'"></div>')
        elif kind=='items':items()
        elif kind=='totals':totals()
        elif kind=='tax':parts.append('<p>Recorded tax: '+text(snapshot.get('totals',{}).get('Tax','Unavailable for this source'))+'</p>')
        else:
            tag='h2' if kind=='title' else 'p';parts.append('<'+tag+'>'+text(block['text'])+'</'+tag+'>')
        placed.add(kind)
    if 'items' not in placed:items()
    if 'totals' not in placed:totals()
    parts.append('<p>Document source '+text(snapshot['source_id'])+'</p></main></body></html>')
    return ''.join(parts)
