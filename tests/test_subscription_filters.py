"""Searching, filtering and sorting the Subscriptions page."""
import re
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Subscription, User

NAMES = ("Netflix", "netflix kids", "Spotify", "Old gym", "Language trial", "Zebra news")


def _register(client, email):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def _add(owner_id, name, renewal, **overrides):
    values = {"price": Decimal("10.00"), "currency": "USD", "billing_cycle": "monthly", "category": "other", **overrides}
    db.session.add(Subscription(user_id=owner_id, name=name, next_renewal_date=renewal, **values))


def _seed(app, client):
    _register(client, "owner@example.com")
    other = app.test_client()
    _register(other, "other@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id).filter_by(email="owner@example.com"))
        other_id = db.session.scalar(db.select(User.id).filter_by(email="other@example.com"))
        _add(owner, "Netflix", date(2030, 3, 1), category="streaming")
        _add(owner, "netflix kids", date(2030, 2, 1), category="streaming", status="paused")
        _add(owner, "Spotify", date(2030, 1, 1), category="music")
        _add(owner, "Old gym", date(2030, 4, 1), category="fitness", status="cancelled")
        _add(owner, "Language trial", date(2030, 5, 1), category="education", subscription_type="trial_converts")
        _add(owner, "Zebra news", date(2030, 6, 1), category="news", subscription_type="trial_ends", status="paused")
        _add(other_id, "Netflix of someone else", date(2030, 1, 1), category="streaming")
        db.session.commit()
    return other


def _shown(client, query=""):
    """Return the card names on the page, in order."""
    html = client.get(f"/subscriptions/{query}").get_data(as_text=True)
    return re.findall(r'<h3 class="h6 mb-1 text-truncate">([^<]+)</h3>', html), html


def test_search_and_filters_narrow_the_list(app, client):
    _seed(app, client)

    names, html = _shown(client)
    # Default order is by next date, and nothing is filtered.
    assert names == ["Spotify", "netflix kids", "Netflix", "Old gym", "Language trial", "Zebra news"]
    assert "Showing" not in html and "Clear filters" not in html

    cases = {
        "?q=netflix": ["netflix kids", "Netflix"],
        "?q=%20NETFLIX%20": ["netflix kids", "Netflix"],
        "?status=paused": ["netflix kids", "Zebra news"],
        "?status=cancelled": ["Old gym"],
        "?kind=trial": ["Language trial", "Zebra news"],
        "?kind=paid": ["Spotify", "netflix kids", "Netflix", "Old gym"],
        "?category=streaming": ["netflix kids", "Netflix"],
        "?q=netflix&status=active": ["Netflix"],
        "?kind=trial&status=paused&category=news": ["Zebra news"],
        "?sort=name": ["Language trial", "Netflix", "netflix kids", "Old gym", "Spotify", "Zebra news"],
        "?category=streaming&sort=name": ["Netflix", "netflix kids"],
    }
    for query, expected in cases.items():
        assert _shown(client, query)[0] == expected, query

    names, html = _shown(client, "?q=netflix&status=paused")
    assert names == ["netflix kids"]
    assert "Showing 1 of 6 subscriptions." in html and "Clear filters" in html
    # The form remembers what was chosen.
    assert re.search(r'<input [^>]*name="q"[^>]*value="netflix"', html)
    assert re.search(r'<option value="paused" selected>Paused</option>', html)

    # Sorting alone is not a filter.
    assert "Showing" not in _shown(client, "?sort=name")[1]


def test_no_matches_and_unknown_values(app, client):
    other = _seed(app, client)

    names, html = _shown(client, "?q=nothing-like-this")
    assert names == []
    assert "No subscriptions match these filters" in html and "No subscriptions yet" not in html
    assert "Showing 0 of 6 subscriptions." in html

    # Values that are not on the lists are ignored instead of causing an error.
    names, html = _shown(client, "?status=deleted&kind=x&category=y&sort=price")
    assert len(names) == 6 and "Showing" not in html

    # Search text is shown back safely and never treated as HTML or a pattern.
    names, html = _shown(client, "?q=%3Cscript%3Ealert(1)%3C/script%3E")
    assert names == [] and "<script>alert(1)" not in html
    assert _shown(client, "?q=%25")[0] == []

    # Filters only ever look at the signed-in account.
    assert _shown(client, "?q=someone")[0] == []
    assert _shown(other, "?q=netflix")[0] == ["Netflix of someone else"]
    assert "Showing 1 of 1 subscription." in _shown(other, "?q=netflix")[1]


def test_an_empty_account_has_no_filter_bar(app, client):
    _register(client, "owner@example.com")
    html = client.get("/subscriptions/?status=paused").get_data(as_text=True)
    assert "No subscriptions yet" in html
    assert 'name="q"' not in html and "No subscriptions match" not in html
