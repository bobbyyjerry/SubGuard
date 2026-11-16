"""Fixed lists used across SubGuard (forms, templates, calculations).

Keeping them in one place means a new category or currency only has to be
added here, and every form and page picks it up.
"""

# key -> (display name, Bootstrap Icons class)
CATEGORIES = {
    "streaming": ("Streaming", "bi-play-btn"),
    "music": ("Music", "bi-music-note-beamed"),
    "software": ("Software", "bi-laptop"),
    "cloud": ("Cloud storage", "bi-cloud"),
    "gaming": ("Gaming", "bi-controller"),
    "news": ("News & reading", "bi-newspaper"),
    "fitness": ("Fitness", "bi-heart-pulse"),
    "education": ("Education", "bi-mortarboard"),
    "other": ("Other", "bi-box"),
}

# key -> (display name, short suffix shown after a price)
BILLING_CYCLES = {
    "weekly": ("Weekly", "/wk"),
    "monthly": ("Monthly", "/mo"),
    "quarterly": ("Every 3 months", "/qtr"),
    "yearly": ("Yearly", "/yr"),
}

# key -> (display name, Bootstrap colour)
STATUSES = {
    "active": ("Active", "success"),
    "paused": ("Paused", "warning"),
    "cancelled": ("Cancelled", "secondary"),
}

# ISO currency code -> symbol
CURRENCIES = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "NGN": "₦",
    "CAD": "CA$",
    "AUD": "A$",
    "INR": "₹",
    "JPY": "¥",
}

# Currencies that have no cents/minor unit.
ZERO_DECIMAL_CURRENCIES = {"JPY"}
