#!/usr/bin/env python3

"""
Regression test for PostsGridView.navigateToPost() (GramAddict/core/views.py).

Root cause of "bot gets stuck scrolling a blogger's profile for minutes doing
nothing": navigateToPost() called target.click() on a grid cell and then
UNCONDITIONALLY returned OpenedPostView(self.device), regardless of whether
the click actually navigated off the grid. nav_to_post_likers() (used by the
"blogger-post-likers" job, e.g. a config.yml listing some
blogger) only bails out when navigateToPost() returns None — so a click
that silently failed to open a post made it think a post was open. handle_likers()
then ran its feed-post scanning loop (_check_if_last_post, _find_likers_container,
swipe_to_fit_posts) against the still-visible profile GRID, where none of that
data exists, forever (two live UI dumps captured 3 minutes apart on the actual
device showed the exact same frozen grid position).

This test verifies navigateToPost() now checks whether the grid marker
(MEDIA_SET_ROW_CONTENT_IDENTIFIER) is still present after the click and
returns None (treated as a failed navigation by every caller) instead of a
bogus OpenedPostView when it is.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), "GramAddict"))

from GramAddict.core import views as views_module
from GramAddict.core.views import PostsGridView


def _make_cell(top, left):
    cell = MagicMock()
    cell.get_bounds.return_value = {"top": top, "left": left, "right": left + 10, "bottom": top + 10}
    cell.get_desc.return_value = "Photo by someone at Row 1, Column 1"
    return cell


def _run_scenario(click_actually_opens_post: bool):
    device = MagicMock()
    cell = _make_cell(0, 0)

    def fake_find(resourceIdMatches=None, **kwargs):
        resourceIdMatches = resourceIdMatches or ""
        result = MagicMock()
        if "IMAGE_BUTTON" in resourceIdMatches:
            result.__iter__.return_value = iter([cell])
        elif "MEDIA_SET_ROW_CONTENT_IDENTIFIER" in resourceIdMatches:
            # If the click really opened a post, the grid marker is gone.
            result.exists.return_value = not click_actually_opens_post
        return result

    device.find.side_effect = fake_find

    with patch.object(views_module, "safe_resource", lambda name: name), patch.object(
        views_module, "random_sleep", lambda *a, **k: None
    ):
        grid_view = PostsGridView(device)
        opened_post_view, media_type, obj_count = grid_view.navigateToPost(0, 0)

    return opened_post_view, cell


def test_failed_click_returns_none_instead_of_fake_opened_post():
    opened_post_view, cell = _run_scenario(click_actually_opens_post=False)
    cell.click.assert_called_once()
    assert opened_post_view is None, (
        "BUG REPRODUCED: navigateToPost() returned a truthy OpenedPostView even "
        "though the grid marker was still present (the click never actually "
        "opened a post) — callers will wrongly believe a post opened."
    )
    print("PASS: a click that doesn't leave the grid is reported as a failure (None).")


def test_successful_click_returns_opened_post_view():
    opened_post_view, cell = _run_scenario(click_actually_opens_post=True)
    cell.click.assert_called_once()
    assert opened_post_view is not None, "A genuinely successful click must still return an OpenedPostView."
    print("PASS: a click that actually leaves the grid still returns an OpenedPostView.")


if __name__ == "__main__":
    test_failed_click_returns_none_instead_of_fake_opened_post()
    test_successful_click_returns_opened_post_view()
