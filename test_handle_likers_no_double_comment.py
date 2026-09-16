#!/usr/bin/env python3

"""
Regression test for the "comments twice in a row on the same post" bug.

Root cause: in handle_likers() (GramAddict/core/handle_sources.py), when the
likers list turns out empty, the code does device.back() and break WITHOUT
calling swipe_to_fit_posts(SwipeTo.NEXT_POST) first (unlike the other two
break points in that same inner loop, which do swipe before breaking). The
outer while loop then lands back on the exact same post and re-runs
_like_and_comment_current_post() on it.

This test simulates a session where the likers list is always reported empty
(inspect_current_view always raises EmptyList) and asserts that no single
post ever gets _like_and_comment_current_post() called on it more than once.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), "GramAddict"))

from GramAddict.core import handle_sources
from GramAddict.core.utils import EmptyList
from GramAddict.core.views import SwipeTo

MAX_POSTS = 3


class _State:
    def __init__(self):
        self.post_index = 0
        self.comment_calls = []
        self.swipe_calls = 0


def _run_scenario():
    state = _State()

    class FakePostsViewList:
        def __init__(self, device):
            pass

        def _check_if_last_post(self, last_description, current_job):
            desc = f"DESC_{state.post_index}"
            flag = desc == last_description
            return flag, desc, f"user_{state.post_index}", False, False, False

        def _find_likers_container(self):
            return True, 50

        def open_likers_container(self):
            return True

        def swipe_to_fit_posts(self, swipe_to):
            if swipe_to == SwipeTo.NEXT_POST:
                state.post_index += 1
                state.swipe_calls += 1

    class FakeOpenedPostView:
        def __init__(self, device):
            pass

        def _getListViewLikers(self):
            # Ends the test deterministically once we've seen enough posts.
            if state.post_index >= MAX_POSTS:
                return None
            return MagicMock()

        def _getUserContainer(self):
            return MagicMock()

    def fake_inspect_current_view(container):
        # Simulates the exact log the user hit: "The likers list is empty".
        raise EmptyList()

    def fake_like_and_comment(
        self_, device, session_state, interaction, post_view_list, media_type=None
    ):
        state.comment_calls.append(state.post_index)

    with patch.object(handle_sources, "PostsViewList", FakePostsViewList), patch.object(
        handle_sources, "OpenedPostView", FakeOpenedPostView
    ), patch.object(
        handle_sources, "inspect_current_view", fake_inspect_current_view
    ), patch.object(
        handle_sources, "nav_to_hashtag_or_place", lambda *a, **k: True
    ), patch.object(
        handle_sources, "_like_and_comment_current_post", fake_like_and_comment
    ):
        profile_filter = MagicMock()
        profile_filter.is_num_likers_in_range.return_value = True

        handle_sources.handle_likers(
            MagicMock(),
            device=MagicMock(),
            session_state=MagicMock(),
            target="testtarget",
            current_job="hashtag-likers",
            storage=MagicMock(),
            profile_filter=profile_filter,
            posts_end_detector=MagicMock(),
            on_interaction=lambda **k: True,
            interaction=MagicMock(),
            is_follow_limit_reached=None,
        )

    return state


def test_no_duplicate_comment_on_same_post():
    state = _run_scenario()
    print(f"Comment calls (by post index): {state.comment_calls}")
    duplicates = {p for p in state.comment_calls if state.comment_calls.count(p) > 1}
    assert not duplicates, (
        f"BUG REPRODUCED: post(s) {sorted(duplicates)} were commented on more "
        f"than once in a row. Full call sequence: {state.comment_calls}"
    )
    print("PASS: no post was commented on more than once.")


if __name__ == "__main__":
    test_no_duplicate_comment_on_same_post()
