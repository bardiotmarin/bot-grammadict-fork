#!/usr/bin/env python3

"""
Regression test for the "bot scrolls a feed for minutes without doing anything"
bug in handle_posts() (GramAddict/core/handle_sources.py).

Root cause: when Instagram's feed row layout changes and _post_owner() can no
longer find the post author, _check_if_last_post() returns an empty username.
The "same post" safety net (nr_same_post) depends on that same detection and
never increments in this case, so nothing used to stop the job: it would
scroll through the entire session without ever taking any action, and
_post_owner(..., Owner.OPEN, "") degrades to a "match anything" selector
(textStartsWith("") matches every string), which is unsafe to click.

This test simulates a feed where the post author can never be identified and
asserts that handle_posts() gives up after a bounded number of consecutive
unidentified posts instead of looping for the rest of the session, and that
it never calls _post_owner(..., Owner.OPEN, ...) with a falsy username.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), "GramAddict"))

from GramAddict.core import handle_sources
from GramAddict.core.views import SwipeTo, Owner

MAX_ITERATIONS = 200  # safety cap so a regression truly hangs the test, not the CI


class _State:
    def __init__(self):
        self.iterations = 0
        self.swipe_calls = 0
        self.post_owner_open_calls = []


def _run_scenario():
    state = _State()

    class FakePostsViewList:
        def __init__(self, device):
            pass

        def _check_if_last_post(self, last_description, current_job):
            state.iterations += 1
            if state.iterations > MAX_ITERATIONS:
                raise AssertionError(
                    "handle_posts() never stopped: it kept scrolling past "
                    f"{MAX_ITERATIONS} posts it could never identify."
                )
            # Simulates the broken layout: author can never be found.
            return False, "", "", False, False, False

        def _find_likers_container(self):
            return False, 0

        def _post_owner(self, current_job, mode, username=None):
            if mode == Owner.OPEN:
                state.post_owner_open_calls.append(username)
            return (False, False, False)

        def swipe_to_fit_posts(self, swipe_to):
            if swipe_to == SwipeTo.NEXT_POST:
                state.swipe_calls += 1

    class FakeOpenedPostView:
        def __init__(self, device):
            pass

        def _is_post_liked(self):
            return False, False

        def start_video(self):
            pass

        def _check_if_liked(self):
            return False

        def _like_in_post_view(self, *a, **k):
            pass

    with patch.object(handle_sources, "PostsViewList", FakePostsViewList), patch.object(
        handle_sources, "OpenedPostView", FakeOpenedPostView
    ), patch.object(handle_sources, "nav_to_hashtag_or_place", lambda *a, **k: True):
        profile_filter = MagicMock()
        profile_filter.is_num_likers_in_range.return_value = False
        profile_filter.is_handler_blacklisted.return_value = False

        storage = MagicMock()
        storage.is_user_in_blacklist.return_value = False
        storage.check_user_was_interacted.return_value = (False, None)

        self_obj = MagicMock()
        self_obj.args.skipped_posts_limit = "5"

        handle_sources.handle_posts(
            self_obj,
            device=MagicMock(),
            session_state=MagicMock(),
            target="testtarget",
            current_job="hashtag-posts-recent",
            storage=storage,
            profile_filter=profile_filter,
            on_interaction=lambda **k: True,
            interaction=MagicMock(),
            is_follow_limit_reached=None,
            interact_percentage=100,
            scraping_file=None,
        )

    return state


def test_handle_posts_gives_up_on_unidentifiable_feed():
    state = _run_scenario()
    print(f"Iterations before stopping: {state.iterations}")
    print(f"_post_owner(..., Owner.OPEN, ...) calls: {state.post_owner_open_calls}")

    assert state.iterations <= MAX_ITERATIONS, (
        "handle_posts() scrolled indefinitely without ever giving up."
    )
    assert not any(
        not u for u in state.post_owner_open_calls
    ), "_post_owner(..., Owner.OPEN, ...) was called with a falsy/empty username."
    print("PASS: handle_posts() stopped instead of scrolling forever, and never "
          "opened a post with an unidentified (empty) username.")


if __name__ == "__main__":
    test_handle_posts_gives_up_on_unidentifiable_feed()
