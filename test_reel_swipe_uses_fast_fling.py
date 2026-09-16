#!/usr/bin/env python3

"""
Regression test for the "feed job stuck on the same Reel for minutes" bug.

Live logs showed swipe_to_fit_posts()'s Reels branch (GramAddict/core/views.py)
reading the identical like count ("Like number is3582") 25+ times in a row over
several minutes: the "full-screen swipe to advance" kept landing back on the
same Reel instead of moving to the next one.

Root cause: DeviceFacade.View.swipe_points() always used a 0.2-0.5s duration for
the gesture (device_facade.py, previously hardcoded). That's a deliberate scroll
motion, not a flick, and Instagram's Reels ViewPager2 requires a genuine
high-velocity fling to cross its page-snap threshold — a slow swipe over a full
screen height gets absorbed as a bounce-back scroll instead of a page change.

Fix: swipe_points() now accepts an optional `duration` override (defaulting to
the original uniform(0.2, 0.5) so every other caller is unaffected), and the
Reels branch of swipe_to_fit_posts() passes a short ~0.06-0.12s duration for a
decisive fling.

This test verifies both the override and the default-preserving behavior;
verifying it actually crosses the fling threshold requires a real device, so a
short/fast duration is a proxy for "these two together" that the code review can
sanity check.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), "GramAddict"))

from GramAddict.core.device_facade import DeviceFacade
from GramAddict.core import views as views_module
from GramAddict.core.views import PostsViewList, SwipeTo


def _make_facade():
    facade = DeviceFacade.__new__(DeviceFacade)
    facade.deviceV2 = MagicMock()
    return facade


def test_swipe_points_default_duration_unchanged():
    facade = _make_facade()
    with patch("GramAddict.core.device_facade.uniform", return_value=0.35), patch.object(
        DeviceFacade, "sleep_mode", staticmethod(lambda mode: None)
    ):
        facade.swipe_points(100, 800, 100, 200, random_x=False, random_y=False)
    args, kwargs = facade.deviceV2.swipe_points.call_args
    duration_used = args[1]
    assert duration_used == 0.35, (
        f"Default swipe_points() call should still use the randomized 0.2-0.5s "
        f"duration when no override is given, got {duration_used}."
    )
    print("PASS: swipe_points() without an override keeps the original duration behavior.")


def test_swipe_points_honors_explicit_duration():
    facade = _make_facade()
    with patch.object(DeviceFacade, "sleep_mode", staticmethod(lambda mode: None)):
        facade.swipe_points(100, 800, 100, 200, random_x=False, random_y=False, duration=0.08)
    args, kwargs = facade.deviceV2.swipe_points.call_args
    duration_used = args[1]
    assert duration_used == 0.08, (
        f"swipe_points() should pass through an explicit duration override, got {duration_used}."
    )
    print("PASS: swipe_points() honors an explicit duration override.")


def test_reel_advance_uses_a_fast_fling_duration():
    device = MagicMock()
    device.get_info.return_value = {"displayWidth": 720, "displayHeight": 1280}

    with patch.object(views_module, "case_insensitive_re", lambda x: x), patch.object(
        views_module, "safe_resource", lambda name: name
    ):
        post_view_list = PostsViewList(device)
        post_view_list._is_on_reel = lambda: True
        post_view_list.swipe_to_fit_posts(SwipeTo.NEXT_POST)

    args, kwargs = device.swipe_points.call_args
    duration_used = kwargs.get("duration")
    assert duration_used is not None, "The Reels branch must pass an explicit duration."
    assert duration_used < 0.2, (
        f"Reel-advance swipe should be a fast fling (<0.2s) to cross the ViewPager2 "
        f"snap threshold, got {duration_used}s — this is what caused the bot to get "
        f"stuck bouncing back to the same Reel for minutes."
    )
    print(f"PASS: Reel-advance swipe uses a fast fling duration ({duration_used:.3f}s).")


if __name__ == "__main__":
    test_swipe_points_default_duration_unchanged()
    test_swipe_points_honors_explicit_duration()
    test_reel_advance_uses_a_fast_fling_duration()
