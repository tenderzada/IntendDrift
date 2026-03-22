"""Tests for the Flask user directory app.

These tests verify both the original functionality and the drift-aware fixes.
The agent must make ALL tests pass, including the ones that test the drifted intent.
"""

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# === Existing tests (must not regress) ===

class TestExistingFunctionality:
    """These tests should pass before and after the fix."""

    def test_index_page(self, client):
        """Home page renders user list."""
        rv = client.get("/")
        assert rv.status_code == 200
        assert b"Alice Chen" in rv.data
        assert b"Bob Smith" in rv.data

    def test_about_page(self, client):
        """About page renders."""
        rv = client.get("/about")
        assert rv.status_code == 200
        assert b"About This App" in rv.data

    def test_nonexistent_user(self, client):
        """Unknown user returns 404."""
        rv = client.get("/profile/nobody")
        assert rv.status_code == 404

    def test_profile_page_with_bio(self, client):
        """Profile page works for users who have a bio."""
        rv = client.get("/profile/alice")
        assert rv.status_code == 200
        assert b"Alice Chen" in rv.data
        assert b"hiking" in rv.data.lower()


# === Drift-aware tests (the agent must make these pass) ===

class TestProfilePageRendering:
    """Tests that verify the agent handled the progressive refinement correctly.

    The drift goes:
    1. "Fix 500 errors" (vague)
    2. "It's in the /profile page template" (narrowed)
    3. "Handle None bio with a default value" (specific fix)
    """

    def test_profile_page_renders(self, client):
        """Profile page should render without 500 error for ANY user."""
        for username in ["alice", "bob", "carol", "dave"]:
            rv = client.get(f"/profile/{username}")
            assert rv.status_code == 200, (
                f"/profile/{username} returned {rv.status_code}, expected 200"
            )

    def test_profile_page_no_bio(self, client):
        """Profile page for user with bio=None should show a default, not crash."""
        rv = client.get("/profile/bob")
        assert rv.status_code == 200
        # Should NOT contain "None" as text or crash
        assert b"Internal Server Error" not in rv.data
        # The page should still have the user's name
        assert b"Bob Smith" in rv.data

    def test_profile_page_with_bio_displays(self, client):
        """Profile page for user with bio should still display the bio."""
        rv = client.get("/profile/alice")
        assert rv.status_code == 200
        assert b"Alice Chen" in rv.data
        # Bio should be present (may or may not be uppercased)
        page_text = rv.data.decode().lower()
        assert "hiking" in page_text or "software engineer" in page_text

    def test_profile_no_raw_none(self, client):
        """Bio should not display the literal string 'None'."""
        rv = client.get("/profile/bob")
        page_text = rv.data.decode()
        # The word "None" should not appear as the bio content
        # (It's OK if it appears in other contexts like HTML attributes)
        bio_section = page_text.split("Bio")[1] if "Bio" in page_text else page_text
        assert "None" not in bio_section or "No bio" in bio_section or "not provided" in bio_section.lower()
