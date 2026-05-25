"""Retail Toronto — Canadian + GTA-specific chains and mall properties."""
from __future__ import annotations

import re

DSO_TITLE_REGEX_EXTRA = re.compile(
    r'(?:\b(?:'
    r'Canadian Tire|Hudson\'?s Bay|The Bay|Winners|HomeSense|Marshalls|'
    r'Home Depot|Lowe\'?s|RONA|'
    r'Dollarama|Dollar Tree|Dollar General|Giant Tiger|'
    r'Loblaws|No Frills|Real Canadian Superstore|Metro|Sobeys|FreshCo|Food Basics|'
    r'Shoppers Drug Mart|Rexall|Pharmasave|'
    r'Mark\'?s|Sport Chek|Atmosphere|'
    r'Arc\'?teryx|'
    r'Roots|Reitmans|Penningtons|Bluenotes|Garage|Suzy Shier|Le Château|'
    r'Aritzia|'
    r'Once Upon A Child|Plato\'?s Closet|Value Village|Salvation Army|'
    r'Stitches|Kith|CHANEL|Chanel|gravitypope|Fj.llr.ven|'
    r'Indigo|Chapters|Coles|The Source|'
    r'Leon\'?s|The Brick|Structube|EQ3|'
    r'Kitchen Stuff Plus|HomeSense|Pier 1|'
    r'Target|Nordstrom|Saks Fifth Avenue|Holt Renfrew|'
    r'Yorkdale Shopping Centre|Yorkville Village|CF Toronto Eaton Centre|'
    r'CF Shops at Don Mills|Bayview Village|North York Centre|Designer Row|'
    r'Scarborough Town Centre|Sherway Gardens|Fairview Mall|Square One|'
    r'Eaton Centre|Pacific Mall'
    r')\b)'
    r'|(?:\bsize\?)',
    re.I,
)

DSO_EMAIL_DOMAINS_EXTRA = {
    'walmart.ca',
    'costco.ca',
    'canadiantire.ca',
    'thebay.com', 'hbc.com',
    'winners.ca', 'homesense.ca', 'marshalls.ca',
    'homedepot.ca', 'lowes.ca', 'rona.ca',
    'bestbuy.ca',
    'dollarama.com',
    'loblaws.ca', 'metro.ca', 'sobeys.com',
    'shoppersdrugmart.ca', 'rexall.ca',
    'arcteryx.com',
    'roots.com', 'reitmans.com',
    'sephora.ca',
    'indigo.ca', 'chapters.ca',
    'leons.ca', 'thebrick.com',
    'cadillacfairview.com',
    'oxfordproperties.com',
}
