"""Default business expense categories used to classify parsed line items.

Kept separate from ai_parser.py so a user can swap in their own taxonomy
(e.g. marketing spend categories) without touching the parsing logic —
just pass a different list into `parse_document`.
"""

DEFAULT_CATEGORIES = [
    "Office Supplies",
    "Software & Subscriptions",
    "Travel",
    "Meals & Entertainment",
    "Equipment & Hardware",
    "Professional Services",
    "Marketing & Advertising",
    "Shipping & Freight",
    "Utilities",
    "Other / Uncategorized",
]
