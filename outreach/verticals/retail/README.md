# Retail vertical — exploratory

Targets small-to-medium independent retail. STL's product (voice
agents + workflow automation) is built for phone-heavy service
businesses; fit on retail is unproven.

## Default vertical_keyword

`boutique` (template-specific — see `query_templates.txt`).

## Adding a retail campaign

Country-specific national chains (Canadian Tire, Loblaws, Apple Stores
in CA) belong in `campaigns/<c>/overrides.py` as
`DSO_TITLE_REGEX_EXTRA`. Mall property listings should be flagged the
same way so the analyze step excludes them from the buyer set.
