"""Day 2: page rendering tests."""


def test_landing_page_has_hero_and_features(client):
    html = client.get("/").get_data(as_text=True)
    assert "Never pay for a forgotten subscription again" in html
    assert "Free-trial tracking" in html
    assert 'href="/dashboard/"' in html  # "See the dashboard" button


def test_navbar_marks_dashboard_active(client):
    html = client.get("/dashboard/").get_data(as_text=True)
    assert 'class="nav-link active" href="/dashboard/"' in html


def test_dashboard_shows_sections_and_sample_data(client):
    response = client.get("/dashboard/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for text in ("Est. monthly spend", "Upcoming payments", "Active free trials", "Your subscriptions"):
        assert text in html
    assert "Netflix" in html
    assert "Preview mode" in html


def test_dashboard_totals_are_per_currency(client):
    html = client.get("/dashboard/").get_data(as_text=True)
    # USD: 15.49 + 11.99 + 2.99 + 16.99 + 239.88/12 (=19.99) = 67.45 ; EUR gym 30.00
    assert "$67.45 + €30.00" in html


def test_delete_forms_carry_csrf_token(client):
    html = client.get("/dashboard/").get_data(as_text=True)
    assert 'name="csrf_token"' in html


def test_custom_404_page(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert "Page not found" in response.get_data(as_text=True)
