import datetime
import logging
import re
import platform
from enum import Enum, auto
from random import choice, randint, uniform
from time import sleep
from typing import Optional, Tuple

import emoji
from colorama import Fore, Style

from GramAddict.core.device_facade import (
    DeviceFacade,
    Direction,
    Location,
    Mode,
    SleepTime,
    Timeout,
)
from GramAddict.core.resources import ClassName
from GramAddict.core.resources import ResourceID as resources
from GramAddict.core.resources import TabBarText
from GramAddict.core.utils import (
    ActionBlockedError,
    Square,
    get_value,
    random_sleep,
    save_crash,
)
from GramAddict.core.ocr import ocr_counter_text_near, parse_counter_with_suffix

logger = logging.getLogger(__name__)


def load_config(config):
    global args
    global configs
    global ResourceID
    args = config.args
    configs = config
    ResourceID = resources(config.args.app_id)


def case_insensitive_re(str_list):
    strings = str_list if isinstance(str_list, str) else "|".join(str_list)
    return f"(?i)({strings})"


class TabBarTabs(Enum):
    HOME = auto()
    SEARCH = auto()
    REELS = auto()
    ORDERS = auto()
    ACTIVITY = auto()
    PROFILE = auto()


class SearchTabs(Enum):
    TOP = auto()
    ACCOUNTS = auto()
    TAGS = auto()
    PLACES = auto()


class FollowStatus(Enum):
    FOLLOW = auto()
    FOLLOWING = auto()
    FOLLOW_BACK = auto()
    REQUESTED = auto()
    NONE = auto()


class SwipeTo(Enum):
    HALF_PHOTO = auto()
    NEXT_POST = auto()


class LikeMode(Enum):
    SINGLE_CLICK = auto()
    DOUBLE_CLICK = auto()


class MediaType(Enum):
    PHOTO = auto()
    VIDEO = auto()
    REEL = auto()
    IGTV = auto()
    CAROUSEL = auto()
    UNKNOWN = auto()


class Owner(Enum):
    OPEN = auto()
    GET_NAME = auto()
    GET_POSITION = auto()


class TabBarView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _getTabBar(self):
        return self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.TAB_BAR),
            className=ClassName.LINEAR_LAYOUT,
        )

    def navigateToHome(self):
        self._navigateTo(TabBarTabs.HOME)
        return HomeView(self.device)

    def navigateToSearch(self):
        self._navigateTo(TabBarTabs.SEARCH)
        return SearchView(self.device)

    def navigateToReels(self):
        self._navigateTo(TabBarTabs.REELS)

    def navigateToOrders(self):
        self._navigateTo(TabBarTabs.ORDERS)

    def navigateToActivity(self):
        self._navigateTo(TabBarTabs.ACTIVITY)

    def navigateToProfile(self):
        self._navigateTo(TabBarTabs.PROFILE)
        return ProfileView(self.device, is_own_profile=True)

    def _get_new_profile_position(self) -> Optional[DeviceFacade.View]:
        buttons = self.device.find(className=ResourceID.BUTTON)
        for button in buttons:
            if button.get_desc() == "Profile":
                return button
        return None

    def _navigateTo(self, tab: TabBarTabs):
        tab_name = tab.name
        logger.debug(f"Navigate to {tab_name}")
        button = None
        UniversalActions.close_keyboard(self.device)

        if tab == TabBarTabs.HOME:
            # Try multiple methods for HOME tab
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.HOME_CONTENT_DESC),
            )
            if not button.exists():
                logger.debug("Home tab not found by description, trying resource ID...")
                button = self.device.find(
                    resourceId="com.instagram.android:id/feed_tab",
                )
            # Fallback for Instagram 412+
            if not button.exists():
                logger.debug("Home tab not found, trying direct resource match...")
                button = self.device.find(
                    resourceIdMatches=case_insensitive_re(ResourceID.FEED_TAB),
                )
            # Last resort - click tab bar child at index 0
            if not button.exists():
                logger.debug("Home tab still not found, trying tab bar child index 0...")
                try:
                    tab_bar = self._getTabBar()
                    if tab_bar.exists(Timeout.SHORT):
                        button = tab_bar.child(index=0)
                except Exception as e:
                    logger.debug(f"Tab bar child access failed: {str(e)}")

        elif tab == TabBarTabs.SEARCH:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.SEARCH_CONTENT_DESC),
            )
            if not button.exists():
                button = self.device.find(
                    resourceId="com.instagram.android:id/search_tab",
                )
            if not button.exists():
                logger.debug("Didn't find search in the tab bar...")
                home_view = self.navigateToHome()
                home_view.navigateToSearch()
                return
        elif tab == TabBarTabs.REELS:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.REELS_CONTENT_DESC),
            )
            if not button.exists():
                button = self.device.find(
                    resourceId="com.instagram.android:id/clips_tab",
                )
        elif tab == TabBarTabs.ORDERS:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.ORDERS_CONTENT_DESC),
            )
        elif tab == TabBarTabs.ACTIVITY:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.ACTIVITY_CONTENT_DESC),
            )
        elif tab == TabBarTabs.PROFILE:
            # Multiple strategies for PROFILE tab
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.PROFILE_CONTENT_DESC),
            )
            if not button.exists():
                logger.debug("Profile tab not found by description, trying resource ID...")
                button = self.device.find(
                    resourceId="com.instagram.android:id/profile_tab",
                )
            # Fallback for Instagram 412+
            if not button.exists():
                logger.debug("Profile tab not found, trying resource match...")
                button = self.device.find(
                    resourceIdMatches=case_insensitive_re(ResourceID.PROFILE_TAB),
                )
            # Last resort - click tab bar child at index 4 (profile is last tab)
            if not button.exists():
                logger.debug("Profile tab still not found, trying tab bar child index 4...")
                try:
                    tab_bar = self._getTabBar()
                    if tab_bar.exists(Timeout.SHORT):
                        button = tab_bar.child(index=4)
                except Exception as e:
                    logger.debug(f"Tab bar child access failed: {str(e)}")

        if button is not None and button.exists(Timeout.MEDIUM):
            logger.debug(f"Found tab {tab_name}, clicking...")
            button.click(sleep=SleepTime.SHORT)
            return

        logger.error(f"Didn't find tab {tab_name} in the tab bar...")
        # Try to save debug info
        try:
            tab_bar = self._getTabBar()
            logger.debug(f"Tab bar exists: {tab_bar.exists()}")
        except Exception as e:
            logger.debug(f"Error checking tab bar: {e}")


class ActionBarView:
    def __init__(self, device: DeviceFacade):
        self.device = device
        self.action_bar = self._getActionBar()

    def _getActionBar(self):
        return self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.ACTION_BAR_CONTAINER),
            className=ClassName.FRAME_LAYOUT,
        )


class HomeView(ActionBarView):
    def __init__(self, device: DeviceFacade):
        super().__init__(device)
        self.device = device

    def navigateToSearch(self):
        logger.debug("Navigate to Search")
        search_btn = self.action_bar.child(
            descriptionMatches=case_insensitive_re(TabBarText.SEARCH_CONTENT_DESC)
        )
        search_btn.click()

        return SearchView(self.device)


class HashTagView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _getRecyclerView(self):
        obj = self.device.find(resourceIdMatches=ResourceID.RECYCLER_VIEW)
        if obj.exists(Timeout.LONG):
            logger.debug("RecyclerView exists.")
        else:
            logger.debug("RecyclerView doesn't exists.")
        return obj

    def _getFistImageView(self, recycler):
        obj = recycler.child(
            resourceIdMatches=ResourceID.IMAGE_BUTTON,
        )
        if obj.exists(Timeout.LONG):
            logger.debug("First image in view exists.")
        else:
            logger.debug("First image in view doesn't exists.")
        return obj

    def _getRecentTab(self):
        obj = self.device.find(
            className=ClassName.TEXT_VIEW,
            textMatches=case_insensitive_re(TabBarText.RECENT_CONTENT_DESC),
        )
        if obj.exists(Timeout.LONG):
            logger.debug("Recent Tab exists.")
        else:
            logger.debug("Recent Tab doesn't exists.")
        return obj


# The place view for the moment It's only a copy/paste of HashTagView
# Maybe we can add the com.instagram.android:id/category_name == "Country/Region" (or other obv)


class PlacesView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _getRecyclerView(self):
        obj = self.device.find(resourceIdMatches=ResourceID.RECYCLER_VIEW)
        if obj.exists(Timeout.LONG):
            logger.debug("RecyclerView exists.")
        else:
            logger.debug("RecyclerView doesn't exists.")
        return obj

    def _getFistImageView(self, recycler):
        obj = recycler.child(
            resourceIdMatches=ResourceID.IMAGE_BUTTON,
        )
        if obj.exists(Timeout.LONG):
            logger.debug("First image in view exists.")
        else:
            logger.debug("First image in view doesn't exists.")
        return obj

    def _getRecentTab(self):
        return self.device.find(
            className=ClassName.TEXT_VIEW,
            textMatches=case_insensitive_re(TabBarText.RECENT_CONTENT_DESC),
        )

    def _getInformBody(self):
        return self.device.find(
            className=ClassName.TEXT_VIEW,
            resourceId=ResourceID.INFORM_BODY,
        )


class SearchView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _getSearchEditText(self):
        for _ in range(2):
            obj = self.device.find(
                resourceIdMatches=case_insensitive_re(
                    ResourceID.ACTION_BAR_SEARCH_EDIT_TEXT
                ),
            )
            if obj.exists(Timeout.LONG):
                return obj
            logger.error(
                "Can't find the search bar! Refreshing it by pressing Home and Search again.."
            )
            UniversalActions.close_keyboard(self.device)
            TabBarView(self.device).navigateToHome()
            TabBarView(self.device).navigateToSearch()
        logger.error("Can't find the search bar!")
        return None

    def _getUsernameRow(self, username):
        return self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.ROW_SEARCH_USER_USERNAME),
            className=ClassName.TEXT_VIEW,
            textMatches=case_insensitive_re(username),
        )

    def _getHashtagRow(self, hashtag):
        return self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.ROW_HASHTAG_TEXTVIEW_TAG_NAME
            ),
            className=ClassName.TEXT_VIEW,
            text=f"#{hashtag}",
        )

    def _getPlaceRow(self):
        obj = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.ROW_PLACE_TITLE),
        )
        obj.wait(Timeout.MEDIUM)
        return obj

    def _getTabTextView(self, tab: SearchTabs):
        tab_layout = self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.FIXED_TABBAR_TABS_CONTAINER
            ),
        )
        if tab_layout.exists():
            logger.debug("Tabs container exists!")
            tab_text_view = tab_layout.child(
                resourceIdMatches=case_insensitive_re(ResourceID.TAB_BUTTON_NAME_TEXT),
                textMatches=case_insensitive_re(tab.name),
            )
            if not tab_text_view.exists():
                logger.debug("Tabs container hasn't text! Let's try with description.")
                for obj in tab_layout.child():
                    if obj.ui_info()["contentDescription"].upper() == tab.name.upper():
                        tab_text_view = obj
                        break
            return tab_text_view
        return None

    def _searchTabWithTextPlaceholder(self, tab: SearchTabs):
        tab_layout = self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.FIXED_TABBAR_TABS_CONTAINER
            ),
        )
        search_edit_text = self._getSearchEditText()

        fixed_text = "Search {}".format(tab.name if tab.name != "TAGS" else "hashtags")
        logger.debug(
            "Going to check if the search bar have as placeholder: {}".format(
                fixed_text
            )
        )

        for item in tab_layout.child(
            resourceId=ResourceID.TAB_BUTTON_FALLBACK_ICON,
            className=ClassName.IMAGE_VIEW,
        ):
            item.click()

            # Little trick for force-update the ui and placeholder text
            if search_edit_text is not None:
                search_edit_text.click()

            if self.device.find(
                className=ClassName.TEXT_VIEW,
                textMatches=case_insensitive_re(fixed_text),
            ).exists():
                return item
        return None

    def navigate_to_target(self, target: str, job: str) -> bool:
        target = emoji.emojize(target, use_aliases=True)
        logger.info(f"Navigate to {target}")
        search_edit_text = self._getSearchEditText()
        if search_edit_text is not None:
            logger.debug("Pressing on searchbar.")
            search_edit_text.click(sleep=SleepTime.SHORT)
        else:
            logger.debug("There is no searchbar!")
            return False
        if self._check_current_view(target, job):
            logger.info(f"{target} is in recent history.")
            return True
        search_edit_text.set_text(
            target,
            Mode.PASTE if args.dont_type else Mode.TYPE,
        )
        if self._check_current_view(target, job):
            logger.info(f"{target} is in top view.")
            return True
        echo_text = self.device.find(resourceId=ResourceID.ECHO_TEXT)
        if echo_text.exists(Timeout.SHORT):
            logger.debug("Pressing on see all results.")
            echo_text.click()
        # at this point we have the tabs available
        self._switch_to_target_tag(job)
        if self._check_current_view(target, job, in_place_tab=True):
            return True
        return False

    def _switch_to_target_tag(self, job: str):
        if "place" in job:
            tab = SearchTabs.PLACES
        elif "hashtag" in job:
            tab = SearchTabs.TAGS
        else:
            tab = SearchTabs.ACCOUNTS

        obj = self._getTabTextView(tab)
        if obj is not None:
            logger.info(f"Switching to {tab.name}")
            obj.click()

    def _check_current_view(
        self, target: str, job: str, in_place_tab: bool = False
    ) -> bool:
        if "place" in job:
            if not in_place_tab:
                return False
            else:
                obj = self._getPlaceRow()
        else:
            obj = self.device.find(
                text=target,
                resourceIdMatches=ResourceID.SEARCH_ROW_ITEM,
            )
        if obj.exists():
            obj.click()
            return True
        return False


class PostsViewList:
    def __init__(self, device: DeviceFacade):
        self.device = device
        self.has_tags = False

    def swipe_to_fit_posts(self, swipe: SwipeTo):
        """calculate the right swipe amount necessary to swipe to next post in hashtag post view
        in order to make it available to other plug-ins I cut it in two moves"""
        displayWidth = self.device.get_info()["displayWidth"]
        containers_content = ResourceID.MEDIA_CONTAINER
        containers_gap = ResourceID.GAP_VIEW_AND_FOOTER_SPACE
        suggested_users = ResourceID.NETEGO_CAROUSEL_HEADER

        # move type: half photo
        if swipe == SwipeTo.HALF_PHOTO:
            zoomable_view_container = self.device.find(
                resourceIdMatches=containers_content
            ).get_bounds()["bottom"]
            ac_exists, _, ac_bottom = PostsViewList(
                self.device
            )._get_action_bar_position()
            if ac_exists and zoomable_view_container < ac_bottom:
                zoomable_view_container += ac_bottom
            self.device.swipe_points(
                displayWidth / 2,
                zoomable_view_container - 5,
                displayWidth / 2,
                zoomable_view_container * 0.5,
            )
        elif swipe == SwipeTo.NEXT_POST:
            logger.info(
                "Scroll down to see next post.", extra={"color": f"{Fore.GREEN}"}
            )
            gap_view_obj = self.device.find(index=-1, resourceIdMatches=containers_gap)
            obj1 = None
            for _ in range(3):
                if not gap_view_obj.exists():
                    logger.debug("Can't find the gap obj, scroll down a little more.")
                    PostsViewList(self.device).swipe_to_fit_posts(SwipeTo.HALF_PHOTO)
                    gap_view_obj = self.device.find(resourceIdMatches=containers_gap)
                    if not gap_view_obj.exists():
                        continue
                    else:
                        break
                else:
                    media = self.device.find(resourceIdMatches=containers_content)
                    if (
                        gap_view_obj.get_bounds()["bottom"]
                        < media.get_bounds()["bottom"]
                    ):
                        PostsViewList(self.device).swipe_to_fit_posts(
                            SwipeTo.HALF_PHOTO
                        )
                        continue
                    suggested = self.device.find(resourceIdMatches=suggested_users)
                    if suggested.exists():
                        for _ in range(2):
                            PostsViewList(self.device).swipe_to_fit_posts(
                                SwipeTo.HALF_PHOTO
                            )
                            footer_obj = self.device.find(
                                resourceIdMatches=ResourceID.FOOTER_SPACE
                            )
                            if footer_obj.exists():
                                obj1 = footer_obj.get_bounds()["bottom"]
                                break
                    break
            if obj1 is None:
                obj1 = gap_view_obj.get_bounds()["bottom"]
            containers_content = self.device.find(resourceIdMatches=containers_content)

            obj2 = (
                (
                    containers_content.get_bounds()["bottom"]
                    + containers_content.get_bounds()["top"]
                )
                * 1
                / 3
            )

            self.device.swipe_points(
                displayWidth / 2,
                obj1 - 5,
                displayWidth / 2,
                obj2 + 5,
            )
            return True

    def _find_likers_container(self):
        universal_actions = UniversalActions(self.device)
        containers_gap = ResourceID.GAP_VIEW_AND_FOOTER_SPACE
        media_container = ResourceID.MEDIA_CONTAINER
        likes = 0
        for _ in range(4):
            gap_view_obj = self.device.find(resourceIdMatches=containers_gap)
            likes_view = self.device.find(
                index=-1,
                resourceId=ResourceID.ROW_FEED_TEXTVIEW_LIKES,
                className=ClassName.TEXT_VIEW,
            )
            description_view = self.device.find(
                resourceIdMatches=ResourceID.ROW_FEED_COMMENT_TEXTVIEW_LAYOUT
            )
            media = self.device.find(
                resourceIdMatches=media_container,
            )
            media_count = media.count_items()
            logger.debug(f"I can see {media_count} media(s) in this view..")

            if media_count > 1 and (
                media.get_bounds()["bottom"]
                < self.device.get_info()["displayHeight"] / 3
            ):
                universal_actions._swipe_points(Direction.DOWN, delta_y=100)
                continue
            if not likes_view.exists():
                if description_view.exists() or gap_view_obj.exists():
                    return False, likes
                else:
                    universal_actions._swipe_points(Direction.DOWN, delta_y=100)
                    continue
            elif media.get_bounds()["bottom"] > likes_view.get_bounds()["bottom"]:
                universal_actions._swipe_points(Direction.DOWN, delta_y=100)
                continue
            logger.debug("Likers container exists!")
            likes = self._get_number_of_likers(likes_view)
            return likes_view.exists(), likes
        return False, 0

    def _get_number_of_likers(self, likes_view):
        likes = 0
        if likes_view.exists():
            likes_view_text = likes_view.get_text().replace(",", "")
            matches_likes = re.search(
                r"(?P<likes>\d+) (?:others|likes)", likes_view_text, re.IGNORECASE
            )
            matches_view = re.search(
                r"(?P<views>\d+) views", likes_view_text, re.IGNORECASE
            )
            if hasattr(matches_likes, "group"):
                likes = int(matches_likes.group("likes"))
                logger.info(
                    f"This post has {likes if 'likes' in likes_view_text else likes + 1} like(s)."
                )
                return likes
            elif hasattr(matches_view, "group"):
                views = int(matches_view.group("views"))
                logger.info(
                    f"I can see only that this post has {views} views(s). It may contain likes.."
                )
                return -1
            else:
                if likes_view_text.endswith("others"):
                    logger.info("This post has more than 1 like.")
                    return -1
                else:
                    logger.info("This post has only 1 like.")
                    likes = 1
                    return likes
        else:
            logger.info("This post has no likes, skip.")
            return likes

    def open_likers_container(self):
        """Open likes container"""
        post_liked_by_a_following = False
        logger.info("Opening post likers.")
        facepil_stub = self.device.find(
            index=-1, resourceId=ResourceID.ROW_FEED_LIKE_COUNT_FACEPILE_STUB
        )

        if facepil_stub.exists():
            logger.debug("Facepile present, pressing on it!")
            facepil_stub.click()
        else:
            random_sleep(1, 2, modulable=False)
            likes_view = self.device.find(
                index=-1,
                resourceId=ResourceID.ROW_FEED_TEXTVIEW_LIKES,
                className=ClassName.TEXT_VIEW,
            )
            if " Liked by" in likes_view.get_text():
                post_liked_by_a_following = True
            elif likes_view.child().count_items() < 2:
                likes_view.click()
                return
            if likes_view.child().exists():
                if post_liked_by_a_following:
                    likes_view.child().click()
                    return
                foil = likes_view.get_bounds()
                hole = likes_view.child().get_bounds()
                try:
                    sq1 = Square(
                        foil["left"],
                        foil["top"],
                        hole["left"],
                        foil["bottom"],
                    ).point()
                    sq2 = Square(
                        hole["left"],
                        foil["top"],
                        hole["right"],
                        hole["top"],
                    ).point()
                    sq3 = Square(
                        hole["left"],
                        hole["bottom"],
                        hole["right"],
                        foil["bottom"],
                    ).point()
                    sq4 = Square(
                        hole["right"],
                        foil["top"],
                        foil["right"],
                        foil["bottom"],
                    ).point()
                except ValueError:
                    logger.debug(f"Point calculation fails: F:{foil} H:{hole}")
                    likes_view.click(Location.RIGHT)
                    return
                sq_list = [sq1, sq2, sq3, sq4]
                available_sq_list = [x for x in sq_list if x == x]
                if available_sq_list:
                    likes_view.click(Location.CUSTOM, coord=choice(available_sq_list))
                else:
                    likes_view.click(Location.RIGHT)
            elif not post_liked_by_a_following:
                likes_view.click(Location.RIGHT)
            else:
                likes_view.click(Location.LEFT)

    def _has_tags(self) -> bool:
        tags_icon = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.INDICATOR_ICON_VIEW)
        )
        self.has_tags = tags_icon.exists()
        return self.has_tags

    def _check_if_last_post(
        self, last_description, current_job
    ) -> Tuple[bool, str, str, bool, bool, bool]:
        """check if that post has been just interacted"""
        universal_actions = UniversalActions(self.device)
        username, is_ad, is_hashtag = PostsViewList(self.device)._post_owner(
            current_job, Owner.GET_NAME
        )
        has_tags = self._has_tags()
        while True:
            post_description = self.device.find(
                index=-1,
                resourceIdMatches=ResourceID.ROW_FEED_TEXT,
                textStartsWith=username,
            )
            if not post_description.exists() and post_description.count_items() >= 1:
                text = post_description.get_text()
                post_description = self.device.find(
                    index=-1,
                    resourceIdMatches=ResourceID.ROW_FEED_TEXT,
                    text=text,
                )
            if post_description.exists():
                logger.debug("Description found!")
                new_description = post_description.get_text().upper()
                if new_description != last_description:
                    return False, new_description, username, is_ad, is_hashtag, has_tags
                logger.info(
                    "This post has the same description and author as the last one."
                )
                return True, new_description, username, is_ad, is_hashtag, has_tags
            else:
                gap_view_obj = self.device.find(resourceId=ResourceID.GAP_VIEW)
                feed_composer = self.device.find(
                    resourceId=ResourceID.FEED_INLINE_COMPOSER_BUTTON_TEXTVIEW
                )
                if gap_view_obj.exists() and gap_view_obj.get_bounds()["bottom"] < (
                    self.device.get_info()["displayHeight"] / 3
                ):
                    universal_actions._swipe_points(
                        direction=Direction.DOWN, delta_y=200
                    )
                    continue
                row_feed_profile_header = self.device.find(
                    resourceId=ResourceID.ROW_FEED_PROFILE_HEADER
                )
                if row_feed_profile_header.count_items() > 1:
                    logger.info("This post hasn't the description...")
                    return False, "", username, is_ad, is_hashtag, has_tags
                profile_header_is_above = row_feed_profile_header.is_above_this(
                    gap_view_obj if gap_view_obj.exists() else feed_composer
                )
                if profile_header_is_above is not None:
                    if not profile_header_is_above:
                        logger.info("This post hasn't the description...")
                        return False, "", username, is_ad, is_hashtag, has_tags

                logger.debug(
                    f"Can't find the description of {username}'s post, try to swipe a little bit down."
                )
                universal_actions._swipe_points(direction=Direction.DOWN, delta_y=200)

    def _if_action_bar_is_over_obj_swipe(self, obj):
        """do a swipe of the amount of the action bar"""
        action_bar_exists, _, action_bar_bottom = PostsViewList(
            self.device
        )._get_action_bar_position()
        if action_bar_exists:
            obj_top = obj.get_bounds()["top"]
            if action_bar_bottom > obj_top:
                UniversalActions(self.device)._swipe_points(
                    direction=Direction.UP, delta_y=action_bar_bottom
                )

    def _get_action_bar_position(self) -> Tuple[bool, int, int]:
        """action bar is overlay, if you press on it, you go back to the first post
        knowing his position is important to avoid it: exists, top, bottom"""
        action_bar = self.device.find(resourceIdMatches=ResourceID.ACTION_BAR_CONTAINER)
        if action_bar.exists():
            return (
                True,
                action_bar.get_bounds()["top"],
                action_bar.get_bounds()["bottom"],
            )
        else:
            return False, 0, 0

    def _refresh_feed(self):
        logger.info("Refresh feed..")
        refresh_pill = self.device.find(resourceId=ResourceID.NEW_FEED_PILL)
        if refresh_pill.exists(Timeout.SHORT):
            refresh_pill.click()
            random_sleep(inf=5, sup=8, modulable=False)
        else:
            UniversalActions(self.device)._reload_page()

    def _post_owner(self, current_job, mode: Owner, username=None):
        """returns a tuple[var, bool, bool]"""
        is_ad = False
        is_hashtag = False
        if username is None:
            post_owner_obj = self.device.find(
                resourceIdMatches=ResourceID.ROW_FEED_PHOTO_PROFILE_NAME
            )
        else:
            for _ in range(2):
                post_owner_obj = self.device.find(
                    resourceIdMatches=ResourceID.ROW_FEED_PHOTO_PROFILE_NAME,
                    textStartsWith=username,
                )
                notification = self.device.find(
                    resourceIdMatches=ResourceID.NOTIFICATION_MESSAGE
                )
                if not post_owner_obj.exists and notification.exists():
                    logger.warning(
                        "There is a notification there! Please disable them in settings.. We will wait 10 seconds before continue.."
                    )
                    sleep(10)
        post_owner_clickable = False

        for _ in range(3):
            if not post_owner_obj.exists():
                if mode == Owner.OPEN:
                    comment_description = self.device.find(
                        resourceIdMatches=ResourceID.ROW_FEED_COMMENT_TEXTVIEW_LAYOUT,
                        textStartsWith=username,
                    )
                    if (
                        not comment_description.exists()
                        and comment_description.count_items() >= 1
                    ):
                        comment_description = self.device.find(
                            resourceIdMatches=ResourceID.ROW_FEED_COMMENT_TEXTVIEW_LAYOUT,
                            text=comment_description.get_text(),
                        )

                    if comment_description.exists():
                        logger.info("Open post owner from description.")
                        comment_description.child().click()
                        return True, is_ad, is_hashtag
                UniversalActions(self.device)._swipe_points(direction=Direction.UP)
                post_owner_obj = self.device.find(
                    resourceIdMatches=ResourceID.ROW_FEED_PHOTO_PROFILE_NAME,
                )
            else:
                post_owner_clickable = True
                break

        if not post_owner_clickable:
            logger.info("Can't find the owner name, skip.")
            return False, is_ad, is_hashtag
        if mode == Owner.OPEN:
            logger.info("Open post owner.")
            PostsViewList(self.device)._if_action_bar_is_over_obj_swipe(post_owner_obj)
            post_owner_obj.click()
            return True, is_ad, is_hashtag
        elif mode == Owner.GET_NAME:
            if current_job == "feed":
                is_ad, is_hashtag, username = PostsViewList(
                    self.device
                )._check_if_ad_or_hashtag(post_owner_obj)
            if username is None:
                username = (
                    post_owner_obj.get_text().replace("•", "").strip().split(" ", 1)[0]
                )
            return username, is_ad, is_hashtag

        elif mode == Owner.GET_POSITION:
            return post_owner_obj.get_bounds(), is_ad
        else:
            return None, is_ad, is_hashtag

    def _get_post_owner_name(self):
        return self.device.find(
            resourceIdMatches=ResourceID.ROW_FEED_PHOTO_PROFILE_NAME
        ).get_text()

    def _get_media_container(self):
        media = self.device.find(resourceIdMatches=ResourceID.CAROUSEL_AND_MEDIA_GROUP)
        content_desc = media.get_desc() if media.exists() else None
        return media, content_desc

    @staticmethod
    def detect_media_type(content_desc) -> Tuple[Optional[MediaType], Optional[int]]:
        """
        Detect the nature and amount of a media
        :return: MediaType and count
        :rtype: MediaType, int
        """
        obj_count = 1
        if content_desc is None:
            return None, None
        if re.match(r"^,|^\s*$", content_desc, re.IGNORECASE):
            logger.info(
                "That media is missing content description, so I don't know which kind of video it is."
            )
            media_type = MediaType.UNKNOWN
        elif re.match(r"^Photo|^Hidden Photo", content_desc, re.IGNORECASE):
            logger.info("It's a photo.")
            media_type = MediaType.PHOTO
        elif re.match(r"^Video|^Hidden Video", content_desc, re.IGNORECASE):
            logger.info("It's a video.")
            media_type = MediaType.VIDEO
        elif re.match(r"^IGTV", content_desc, re.IGNORECASE):
            logger.info("It's a IGTV.")
            media_type = MediaType.IGTV
        elif re.match(r"^Reel", content_desc, re.IGNORECASE):
            logger.info("It's a Reel.")
            media_type = MediaType.REEL
        else:
            carousel_obj = re.finditer(
                r"((?P<photo>\d+) photo)|((?P<video>\d+) video)",
                content_desc,
                re.IGNORECASE,
            )
            n_photos = 0
            n_videos = 0
            for match in carousel_obj:
                if match.group("photo"):
                    n_photos = int(match.group("photo"))
                if match.group("video"):
                    n_videos = int(match.group("video"))
            logger.info(
                f"It's a carousel with {n_photos} photo(s) and {n_videos} video(s)."
            )
            obj_count = n_photos + n_videos
            media_type = MediaType.CAROUSEL
        return media_type, obj_count

    def _like_in_post_view(
        self,
        mode: LikeMode,
        skip_media_check: bool = False,
        already_watched: bool = False,
    ):
        post_view_list = PostsViewList(self.device)
        opened_post_view = OpenedPostView(self.device)
        if skip_media_check:
            return
        media, content_desc = self._get_media_container()
        if content_desc is None:
            return
        if not already_watched:
            media_type, _ = post_view_list.detect_media_type(content_desc)
            opened_post_view.watch_media(media_type)
        if mode == LikeMode.DOUBLE_CLICK:
            if media_type in (MediaType.CAROUSEL, MediaType.PHOTO):
                logger.info("Double click on post.")
                _, _, action_bar_bottom = PostsViewList(
                    self.device
                )._get_action_bar_position()
                media.double_click(obj_over=action_bar_bottom)
            else:
                self._like_in_post_view(
                    mode=LikeMode.SINGLE_CLICK, skip_media_check=True
                )
        elif mode == LikeMode.SINGLE_CLICK:
            like_button_exists, _ = self._find_likers_container()
            if like_button_exists:
                logger.info("Clicking on the little heart ❤️.")
                self.device.find(
                    resourceIdMatches=ResourceID.ROW_FEED_BUTTON_LIKE
                ).click()

    def _follow_in_post_view(self):
        logger.info("Follow blogger in place.")
        self.device.find(resourceIdMatches=ResourceID.BUTTON).click()

    def _comment_in_post_view(self):
        logger.info("Open comments of post.")
        self.device.find(resourceIdMatches=ResourceID.ROW_FEED_BUTTON_COMMENT).click()

    def _check_if_liked(self):
        logger.debug("Check if like succeeded in post view.")
        bnt_like_obj = self.device.find(
            resourceIdMatches=ResourceID.ROW_FEED_BUTTON_LIKE
        )
        if bnt_like_obj.exists():
            STR = "Liked"
            if self.device.find(descriptionMatches=case_insensitive_re(STR)).exists():
                logger.debug("Like is present.")
                return True
            else:
                logger.debug("Like is not present.")
                return False
        else:
            UniversalActions(self.device)._swipe_points(
                direction=Direction.DOWN, delta_y=100
            )
            return PostsViewList(self.device)._check_if_liked()

    def _check_if_ad_or_hashtag(
        self, post_owner_obj
    ) -> Tuple[bool, bool, Optional[str]]:
        is_hashtag = False
        is_ad = False
        logger.debug("Checking if it's an AD or an hashtag..")
        ad_like_obj = post_owner_obj.sibling(
            resourceId=ResourceID.SECONDARY_LABEL,
        )

        owner_name = post_owner_obj.get_text() or post_owner_obj.get_desc() or ""
        if not owner_name:
            logger.info("Can't find the owner name, need to use OCR.")
            try:
                import pytesseract as pt

                owner_name = self.get_text_from_screen(pt, post_owner_obj)
            except ImportError:
                logger.error(
                    "You need to install pytesseract (the wrapper: pip install pytesseract) in order to use OCR feature."
                )
            except pt.TesseractNotFoundError:
                logger.error(
                    "You need to install Tesseract (the engine: it depends on your system) in order to use OCR feature."
                )
        if owner_name.startswith("#"):
            is_hashtag = True
            logger.debug("Looks like an hashtag, skip.")
        if ad_like_obj.exists():
            sponsored_txt = "Sponsored"
            ad_like_txt = ad_like_obj.get_text() or ad_like_obj.get_desc()
            if ad_like_txt.casefold() == sponsored_txt.casefold():
                logger.debug("Looks like an AD, skip.")
                is_ad = True
            elif is_hashtag:
                owner_name = owner_name.split("•")[0].strip()

        return is_ad, is_hashtag, owner_name

    def get_text_from_screen(self, pt, obj) -> Optional[str]:

        if platform.system() == "Windows":
            pt.pytesseract.tesseract_cmd = (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            )

        screenshot = self.device.screenshot()
        bounds = obj.ui_info().get("visibleBounds", None)
        if bounds is None:
            logger.info("Can't find the bounds of the object.")
            return None
        screenshot_cropped = screenshot.crop(
            [
                bounds.get("left"),
                bounds.get("top"),
                bounds.get("right"),
                bounds.get("bottom"),
            ]
        )
        return pt.image_to_string(screenshot_cropped).split(" ")[0].rstrip()


# (rest of file unchanged; only patched import + getFollowersCount/getFollowingCount)
