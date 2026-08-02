import logging

from colorama import Fore

from GramAddict.core.device_facade import Timeout
from GramAddict.core.resources import ClassName
from GramAddict.core.views import (
    HashTagView,
    PlacesView,
    PostsGridView,
    ProfileView,
    TabBarView,
)

logger = logging.getLogger(__name__)


def check_if_english(device):
    """check if app is in English"""
    logger.debug("Checking if app is in English..")
    
    # We essentially want to verify if the "Posts", "Followers", "Following" labels exist in English.
    # Since we can't rely on specific resource IDs returning the labels (they might return numbers),
    # we search for the text directly.
    
    posts = device.find(className=ClassName.TEXT_VIEW, textMatches="(?i)^posts$")
    followers = device.find(className=ClassName.TEXT_VIEW, textMatches="(?i)^followers$")
    following = device.find(className=ClassName.TEXT_VIEW, textMatches="(?i)^following$")

    if posts.exists() and followers.exists() and following.exists():
        logger.debug("Instagram in English.")
    else:
        # Fallback: strict check failed, try lenient or warn
        logger.warning(
            "Could not find 'Posts', 'Followers', 'Following' labels. "
            "Please ensure Instagram is in English. Continuing..."
        )
        # We don't exit here because layout changes might hide the labels or they might be "Post" (singular)
        # But strictly speaking, the bot often relies on English texts for scraping.

    return ProfileView(device, is_own_profile=True)


def nav_to_blogger(device, username, current_job):
    """navigate to blogger (followers list or posts)"""
    _to_followers = bool(current_job.endswith("followers"))
    _to_following = bool(current_job.endswith("following"))
    if username is None:
        profile_view = TabBarView(device).navigateToProfile()
        if _to_followers:
            logger.info("Open your followers.")
            profile_view.navigateToFollowers()
        elif _to_following:
            logger.info("Open your following.")
            profile_view.navigateToFollowing()
    else:
        search_view = TabBarView(device).navigateToSearch()
        if not search_view.navigate_to_target(username, current_job):
            return False

        profile_view = ProfileView(device, is_own_profile=False)
        if _to_followers:
            logger.info(f"Open @{username} followers.")
            return profile_view.navigateToFollowers()
        elif _to_following:
            logger.info(f"Open @{username} following.")
            return profile_view.navigateToFollowing()

    return True


def nav_to_hashtag_or_place(device, target, current_job):
    """navigate to hashtag/place/feed list"""
    search_view = TabBarView(device).navigateToSearch()
    if not search_view.navigate_to_target(target, current_job):
        return False

    TargetView = HashTagView if current_job.startswith("hashtag") else PlacesView

    if current_job.endswith("recent"):
        recent_tab = TargetView(device)._getRecentTab()
        if recent_tab.exists(Timeout.MEDIUM):
            logger.info("Switching to Recent tab.")
            recent_tab.click()
        else:
            # IG >=412 dropped the Top/Recent tabs: the hashtag/place page opens
            # straight onto a single grid. Keep going instead of aborting the job.
            logger.info("No Recent tab on this Instagram version, using the default grid.")

    # An empty result set is caught by the grid check below. Give the grid a
    # real beat to render before reading it — an instant check here caught
    # popular hashtags like #dance or #serato mid-load and wrongly reported
    # "no results", right after switching tabs or landing on the default grid.
    result_view = TargetView(device)._getRecyclerView()
    FistImageInView = TargetView(device)._getFistImageView(result_view)
    if FistImageInView.exists(Timeout.MEDIUM):
        logger.info(f"Opening the first result for {target}.")
        FistImageInView.click()
        return True
    else:
        logger.info(
            f"There is any result for {target} (not exists or doesn't load). Skip."
        )
        return False


def nav_to_post_likers(device, username, my_username):
    """navigate to blogger post likers"""
    if username == my_username:
        TabBarView(device).navigateToProfile()
    else:
        search_view = TabBarView(device).navigateToSearch()
        if not search_view.navigate_to_target(username, "account"):
            return False
    profile_view = ProfileView(device)
    is_private = profile_view.isPrivateAccount()
    posts_count = profile_view.getPostsCount()
    is_empty = posts_count == 0
    if is_private or is_empty:
        private_empty = "Private" if is_private else "Empty"
        logger.info(f"{private_empty} account.", extra={"color": f"{Fore.GREEN}"})
        return False
    logger.info(f"Opening the first post of {username}.")
    ProfileView(device).swipe_to_fit_posts()
    opened_post_view, _, _ = PostsGridView(device).navigateToPost(0, 0)
    if opened_post_view is None:
        # navigateToPost's return value used to be discarded here: if the
        # click silently failed (grid not rendered yet, no posts on screen,
        # ...) this returned True anyway and the caller went on to scroll
        # through what it wrongly assumed was an opened single post — really
        # still the 3-column thumbnail grid, where none of that scrolling
        # logic finds anything. It just spun in place indefinitely.
        logger.warning(f"Could not open {username}'s first post.")
        return False
    return True


def nav_to_feed(device):
    TabBarView(device).navigateToHome()
