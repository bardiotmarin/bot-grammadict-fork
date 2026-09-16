import hashlib
import logging
import os
import re
from collections import Counter
from enum import Enum, auto
from random import randint, uniform
from typing import Optional, Tuple, Any
import emoji
from colorama import Fore
from PIL import Image

from GramAddict.core.device_facade import (
    DeviceFacade,
    Direction,
    Location,
    Mode,
    SleepTime,
    Timeout,
)
from GramAddict.core.resources import ClassName
from GramAddict.core.resources import ContentDescription as Tab
from GramAddict.core.resources import ResourceID as resources
from GramAddict.core.resources import TabBarText

from GramAddict.core.utils import (
    get_value,
    random_sleep,
)
from GramAddict.core.actions import UniversalActions

logger = logging.getLogger(__name__)

args = None
configs = None
ResourceID = resources

def load_config(config):
    global args
    global configs
    global ResourceID
    args = config.args
    configs = config
    try:
        ResourceID = resources(config.args.app_id)
    except Exception as e:
        logger.error(f"Failed to initialize ResourceID: {e}")
        ResourceID = resources

def safe_resource(name):
    """Retourne la ressource ou une chaîne vide safe si introuvable, évite les NoneType"""
    val = getattr(ResourceID, name, "")
    return val if val is not None else ""

def case_insensitive_re(str_list):
    if not str_list:
        return ""
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
        # A missing tab bar is completely normal here: this is a plain lookup,
        # not a "we must be on a main tab" assertion. Most callers are several
        # screens deep (a followers list, an opened post, ...) where the tab bar
        # simply isn't on screen — that's not something to recover from. The one
        # caller that actually needs the tab bar (_navigateTo) already has its own
        # attempt-limited back-press recovery loop; duplicating it here caused
        # over-eager backing out of legitimate, unrelated navigation.
        view = self.device.find(
            resourceIdMatches=case_insensitive_re(safe_resource('TAB_BAR')),
            className=ClassName.LINEAR_LAYOUT,
        )
        if view.exists(): return view

        # Fallback: search without class name constraint
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('TAB_BAR')))

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
        buttons = self.device.find(className=safe_resource('BUTTON'))
        for button in buttons:
            if button.get_desc() == "Profile":
                return button
        return None

    def _navigateTo(self, tab: TabBarTabs):
        tab_name = tab.name
        logger.debug(f"Navigate to {tab_name}")
        button = None
        UniversalActions.close_keyboard(self.device)

        # Helper to find by description
        def find_by_desc(desc_list):
            return self.device.find(descriptionMatches=case_insensitive_re(desc_list))

        for attempt in range(4):
            if tab == TabBarTabs.HOME:
                button = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('FEED_TAB')))
                if not button.exists():
                    button = find_by_desc(Tab.HOME)
                if not button.exists():
                    button = self.device.find(descriptionMatches=case_insensitive_re(TabBarText.HOME_CONTENT_DESC))

            elif tab == TabBarTabs.SEARCH:
                button = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('SEARCH_TAB')))
                if not button.exists():
                    button = find_by_desc(Tab.SEARCH)
                if not button.exists():
                    button = self.device.find(descriptionMatches=case_insensitive_re(TabBarText.SEARCH_CONTENT_DESC))
                if not button.exists():
                    button = self.device.find(descriptionMatches=case_insensitive_re("Search and explore"))
                
            elif tab == TabBarTabs.REELS:
                button = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('REELS_TAB')))
                if not button.exists():
                    button = find_by_desc(Tab.REELS)
                if not button.exists():
                    button = self.device.find(descriptionMatches=case_insensitive_re(TabBarText.REELS_CONTENT_DESC))

            elif tab == TabBarTabs.ORDERS:
                 button = self.device.find(descriptionMatches=case_insensitive_re(TabBarText.ORDERS_CONTENT_DESC))

            elif tab == TabBarTabs.ACTIVITY:
                button = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ACTIVITY_TAB')))
                if not button.exists():
                    button = find_by_desc(Tab.ACTIVITY)
                if not button.exists():
                    button = self.device.find(descriptionMatches=case_insensitive_re(TabBarText.ACTIVITY_CONTENT_DESC))

            elif tab == TabBarTabs.PROFILE:
                button = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('PROFILE_TAB')))
                if not button.exists():
                    button = find_by_desc(Tab.PROFILE)
                if not button.exists():
                    button = self.device.find(descriptionMatches=case_insensitive_re(TabBarText.PROFILE_CONTENT_DESC))

            if button and button.exists(Timeout.MEDIUM):
                logger.debug(f"Found tab {tab_name}, clicking...")
                button.click(sleep=SleepTime.SHORT)
                return

            # Fallback: Try to find the specific tab bar container and click by index
            logger.info(f"Using fallback index navigation for {tab_name}")
            tab_bar = self._getTabBar()
            if tab_bar.exists(Timeout.MEDIUM):
                # Instagram v412 order: Home, Reels, Message, Search, Profile
                index_map = {
                    TabBarTabs.HOME: 0,
                    TabBarTabs.REELS: 1,
                    TabBarTabs.ACTIVITY: 2, # Message/Direct tab
                    TabBarTabs.SEARCH: 3, 
                    TabBarTabs.PROFILE: 4
                }
                idx = index_map.get(tab)
                if idx is not None:
                    child = tab_bar.child(index=idx)
                    if child.exists():
                        child.click(sleep=SleepTime.SHORT)
                        return

            if attempt < 3:
                logger.debug(f"Didn't find tab {tab_name}, pressing back to recover tab bar...")
                self.device.back()

        logger.error(f"Didn't find tab {tab_name} in the tab bar...")

class ActionBarView:
    def __init__(self, device: DeviceFacade):
        self.device = device
        self.action_bar = self._getActionBar()

    def _getActionBar(self):
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ACTION_BAR_CONTAINER')), className=ClassName.FRAME_LAYOUT)

class HomeView(ActionBarView):
    def __init__(self, device: DeviceFacade):
        super().__init__(device)
        self.device = device

    def navigateToSearch(self):
        logger.debug("Navigate to Search")
        search_btn = self.action_bar.child(descriptionMatches=case_insensitive_re(TabBarText.SEARCH_CONTENT_DESC))
        search_btn.click()
        return SearchView(self.device)

class HashTagView:
    def __init__(self, device: DeviceFacade):
        self.device = device
    def _getRecyclerView(self):
        return self.device.find(resourceIdMatches=safe_resource('RECYCLER_VIEW'))
    def _getFistImageView(self, recycler):
        return recycler.child(resourceIdMatches=safe_resource('IMAGE_BUTTON'))
    def _getRecentTab(self):
        return self.device.find(className=ClassName.TEXT_VIEW, textMatches=case_insensitive_re(TabBarText.RECENT_CONTENT_DESC))

class PlacesView:
    def __init__(self, device: DeviceFacade):
        self.device = device
    def _getRecyclerView(self):
        return self.device.find(resourceIdMatches=safe_resource('RECYCLER_VIEW'))
    def _getFistImageView(self, recycler):
        return recycler.child(resourceIdMatches=safe_resource('IMAGE_BUTTON'))
    def _getRecentTab(self):
        return self.device.find(className=ClassName.TEXT_VIEW, textMatches=case_insensitive_re(TabBarText.RECENT_CONTENT_DESC))
    def _getInformBody(self):
        return self.device.find(className=ClassName.TEXT_VIEW, resourceId=safe_resource('INFORM_BODY'))

class SearchView:
    def __init__(self, device: DeviceFacade):
        self.device = device
    @staticmethod
    def _is_main_search_field(obj) -> bool:
        """True unless this EditText belongs to a bottom sheet (likers, comments, ...)."""
        try:
            res = obj.viewV2.info.get("resourceName") or ""
        except Exception:
            return True
        if not res:
            return True
        return "action_bar_search_edit_text" in res

    def _getSearchEditText(self):
        for attempt in range(2):
            # Try by strict resource ID first. Only the FIRST attempt needs to
            # wait it out (Timeout.MEDIUM) for the tab transition to settle —
            # after an explicit recovery navigation below, the field is either
            # there or it isn't, so don't pay this wait twice.
            obj = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ACTION_BAR_SEARCH_EDIT_TEXT')))
            if obj.exists(Timeout.MEDIUM if attempt == 0 else Timeout.SHORT): return obj

            # Fallback 1: By EditText class — but only the real search bar. Bottom
            # sheets (likers, comments) carry their own EditText and typing a
            # hashtag in there searches the wrong list.
            obj_fallback = self.device.find(className=ClassName.EDIT_TEXT)
            if obj_fallback.exists(Timeout.TINY) and self._is_main_search_field(obj_fallback):
                return obj_fallback

            # Fallback 2: Instagram sometimes uses AutoCompleteTextView for search now
            obj_fallback_auto = self.device.find(className="android.widget.AutoCompleteTextView")
            if obj_fallback_auto.exists(Timeout.TINY): return obj_fallback_auto

            # Fallback 3: Any element with 'Search' hint/content-desc
            obj_desc = self.device.find(descriptionMatches=case_insensitive_re(Tab.SEARCH))
            if obj_desc.exists(): return obj_desc
            obj_text = self.device.find(textMatches=case_insensitive_re(Tab.SEARCH))
            if obj_text.exists(): return obj_text

            # Recovery: we should already be ON the search screen at this point
            # (that's the whole reason we're hunting for its edit text) — the
            # field is just slow to render or momentarily unfocused. Calling
            # TabBarView.navigateToSearch() here used to re-run its own full
            # 4-attempt tab-navigation loop (worst case ~20s) on top of the one
            # the caller already paid for, which is where most of the "search
            # takes over a minute" cost was coming from. A tap + short wait is
            # enough to nudge a stuck render without that cost.
            if attempt == 0:
                logger.debug("Search EditText not found, giving the search screen a moment to render...")
                random_sleep(1, 1.5, modulable=False)
        return None
    def _getUsernameRow(self, username):
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_SEARCH_USER_USERNAME')), className=ClassName.TEXT_VIEW, textMatches=case_insensitive_re(username))
    def _getHashtagRow(self, hashtag):
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_HASHTAG_TEXTVIEW_TAG_NAME')), className=ClassName.TEXT_VIEW, text=f"#{hashtag}")
    def _getPlaceRow(self, target: str = None):
        # Try by resource-id first (works on older IG)
        obj = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_PLACE_TITLE')))
        obj.wait(Timeout.SHORT)
        if obj.exists():
            return obj
        # IG v412 fallback: find the first clickable item in search results list
        # Try to find by text matching the target name
        if target:
            obj_txt = self.device.find(textMatches=case_insensitive_re(target))
            if obj_txt.exists(Timeout.SHORT):
                return obj_txt
        # Last resort: find first item in the recycler view results
        recycler = self.device.find(resourceId="com.instagram.android:id/recycler_view")
        if recycler.exists(Timeout.SHORT):
            first_child = recycler.child(index=0)
            if first_child.exists():
                return first_child
        return obj
    def _getTabTextView(self, tab: SearchTabs):
        tab_name = tab.name.capitalize()  # "Accounts", "Tags", "Places"
        # 1. Try by text anywhere on screen (works on IG v412)
        obj = self.device.find(textMatches=case_insensitive_re(tab_name))
        if obj.exists(Timeout.SHORT):
            return obj
        # 2. Try by content-desc
        obj_desc = self.device.find(descriptionMatches=case_insensitive_re(tab_name))
        if obj_desc.exists(Timeout.SHORT):
            return obj_desc
        # 3. Fallback: try uppercase
        obj_upper = self.device.find(textMatches=case_insensitive_re(tab.name))
        if obj_upper.exists(Timeout.SHORT):
            return obj_upper
        return None
    def _searchTabWithTextPlaceholder(self, tab: SearchTabs):
        tab_layout = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('FIXED_TABBAR_TABS_CONTAINER')))
        search_edit_text = self._getSearchEditText()
        fixed_text = "Search {}".format(tab.name if tab.name != "TAGS" else "hashtags")
        for item in tab_layout.child(resourceId=safe_resource('TAB_BUTTON_FALLBACK_ICON'), className=ClassName.IMAGE_VIEW):
            item.click()
            if search_edit_text is not None: search_edit_text.click()
            if self.device.find(className=ClassName.TEXT_VIEW, textMatches=case_insensitive_re(fixed_text)).exists(): return item
        return None
    def navigate_to_target(self, target: str, job: str) -> bool:
        target = emoji.emojize(target, language='alias')
        search_edit_text = self._getSearchEditText()
        if search_edit_text is None:
            logger.warning("navigate_to_target: search EditText not found, cannot type target.")
            return False
        
        # Click to focus the search box
        search_edit_text.click(sleep=SleepTime.SHORT)
        random_sleep(0.3, 0.5, modulable=False)
        
        # After clicking, re-fetch to ensure we have the real focused EditText
        real_search_edit_text = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ACTION_BAR_SEARCH_EDIT_TEXT')))
        if real_search_edit_text.exists(Timeout.SHORT):
            search_edit_text = real_search_edit_text
        else:
            real_et = self.device.find(className=ClassName.EDIT_TEXT)
            if real_et.exists(Timeout.SHORT):
                search_edit_text = real_et
        
        # Clear field using UIAutomator set_text('') - confirmed working on MEmu
        logger.debug(f"Clearing search field before typing: {target}")
        try:
            search_edit_text.set_text("", Mode.PASTE)
            random_sleep(0.3, 0.4, modulable=False)
        except Exception:
            pass
        
        logger.debug(f"Setting search target: {target}")
        search_edit_text.set_text(target, Mode.PASTE)
        random_sleep(1.5, 2, modulable=False)

        # The Accounts/Tags/Places tab row only renders once the search is
        # actually submitted — while merely typing, IG only shows a live
        # autocomplete/"For you" panel that doesn't carry those tabs. Submitting
        # first is what lets us reliably find and click the right tab below.
        self.device.deviceV2.press("search")
        random_sleep(1, 1.5, modulable=False)

        # IMPORTANT: Switch to the correct tab FIRST, then look for the result.
        # Do NOT call _check_current_view before switching — 'For you' tab has unrelated
        # content that matches text searches and causes wrong navigation.
        echo_text = self.device.find(resourceId=safe_resource('ECHO_TEXT'))
        if echo_text.exists(Timeout.SHORT): echo_text.click()

        # Poll for the tab row instead of a single fixed-delay check — it can take
        # a moment to render after submitting. Plain account/username searches never
        # show a tab row at all (results land directly below the search box), so
        # don't bother polling for one there.
        is_account_search = "place" not in job and "hashtag" not in job
        if not is_account_search:
            tab = SearchTabs.PLACES if "place" in job else SearchTabs.TAGS
            switched = False
            for _ in range(4):
                obj = self._getTabTextView(tab)
                if obj is not None:
                    logger.debug(f"Switching to the {tab.name} search tab.")
                    obj.click()
                    switched = True
                    break
                random_sleep(0.5, 1, modulable=False)
            if not switched:
                logger.warning(f"Could not find the {tab.name} search tab.")

        random_sleep(1.5, 2, modulable=False)
        if self._check_current_view(target, job, in_place_tab=True): return True
        # One more wait + retry
        random_sleep(1, 1.5, modulable=False)
        if self._check_current_view(target, job, in_place_tab=True): return True
        return False


    def _check_current_view(self, target: str, job: str, in_place_tab: bool = False) -> bool:
        # Instagram says so explicitly when a search has zero matches (deleted/
        # renamed/mistyped account, dead hashtag, ...). Trust it instead of
        # falling through to "click whatever is the first row" below, which
        # would blindly open an unrelated suggestion and misreport it as a hit.
        if self.device.find(textMatches=case_insensitive_re("No results found.*")).exists(Timeout.TINY):
            logger.info(f"No results found for '{target}'. Skip.")
            return False
        if "place" in job:
            obj = self._getPlaceRow(target)
        elif "hashtag" in job:
            # Hashtags: look for #hashtag text in the Tags tab results
            clean_tag = target.lstrip("#")
            obj = self.device.find(text=f"#{clean_tag}")
            if not obj.exists():
                obj = self.device.find(textMatches=case_insensitive_re(f"#{clean_tag}"))
            if not obj.exists():
                obj = self.device.find(text=clean_tag)
            if not obj.exists():
                obj = self.device.find(textMatches=case_insensitive_re(clean_tag))
            # Fallback: click first row in RecyclerView
            if not obj.exists():
                recycler = self.device.find(resourceId="com.instagram.android:id/recycler_view")
                if recycler.exists(Timeout.SHORT):
                    first_row = recycler.child(index=0)
                    if first_row.exists():
                        logger.debug(f"Hashtag: clicking top result row for '#{clean_tag}'")
                        first_row.click()
                        return True
        else:
            # Account search: look for exact username or first row in RecyclerView
            obj = self.device.find(
                resourceIdMatches=case_insensitive_re(safe_resource('ROW_SEARCH_USER_USERNAME')),
                textMatches=case_insensitive_re(target)
            )
            if not obj.exists():
                recycler = self.device.find(resourceId="com.instagram.android:id/recycler_view")
                if recycler.exists(Timeout.SHORT):
                    obj = recycler.child(text=target)
                    if not obj.exists():
                        obj = recycler.child(textMatches=case_insensitive_re(target))
                    if not obj.exists():
                        first_row = recycler.child(index=0)
                        if first_row.exists():
                            logger.debug(f"Account: clicking top result row for '{target}'")
                            first_row.click()
                            return True

        if obj.exists():
            logger.debug(f"Found result for '{target}', clicking...")
            obj.click()
            return True
        return False


class PostsViewList:
    def __init__(self, device: DeviceFacade):
        self.device = device
        self.has_tags = False
    def _is_on_reel(self) -> bool:
        return self.device.find(
            resourceIdMatches=case_insensitive_re(safe_resource('VIDEO_CONTAINER_AND_CLIPS_VIDEO_CONTAINER'))
        ).exists()

    def swipe_to_fit_posts(self, swipe: SwipeTo):
        try:
            displayWidth = self.device.get_info()["displayWidth"]
            displayHeight = self.device.get_info()["displayHeight"]
            containers_content = safe_resource('MEDIA_CONTAINER')
            containers_gap = safe_resource('GAP_VIEW_AND_FOOTER_SPACE')
            is_reel = self._is_on_reel()

            if swipe == SwipeTo.HALF_PHOTO:
                if is_reel:
                    # Reels are full-screen: there is no "half photo" reveal to do.
                    logger.info("On a Reel, skipping half-photo swipe.")
                    return True
                media_container = self.device.find(resourceIdMatches=containers_content)
                if media_container.exists():
                    zoomable_view_container = media_container.get_bounds()["bottom"]
                    ac_exists, _, ac_bottom = self._get_action_bar_position()
                    if ac_exists and zoomable_view_container < ac_bottom:
                        zoomable_view_container += ac_bottom
                    self.device.swipe_points(displayWidth / 2, zoomable_view_container - 5, displayWidth / 2, zoomable_view_container * 0.5)
                else:
                    # IG >=412 doesn't expose the legacy media container, so this
                    # "reveal the caption" half-swipe has nothing accurate to target.
                    # Doing a blind fallback swipe here just stacks with the NEXT_POST
                    # swipe that follows it and produces erratic, inconsistent scrolling
                    # (sometimes skipping a post, sometimes landing back on the same one).
                    # Skip it — NEXT_POST's own fallback already handles the transition.
                    logger.debug("Media container not found, skipping half-photo swipe.")
                    return True

            elif swipe == SwipeTo.NEXT_POST:
                logger.info("Scroll down to see next post.", extra={"color": f"{Fore.GREEN}"})
                if is_reel:
                    # Reels page on a near full-screen fling; a partial swipe doesn't
                    # cross Instagram's ViewPager2 snap threshold and bounces back
                    # to the same reel.
                    logger.info("On a Reel, using full-screen swipe to advance.")
                    self.device.swipe_points(
                        displayWidth / 2,
                        displayHeight * 0.85,
                        displayWidth / 2,
                        displayHeight * 0.15,
                        duration=uniform(0.06, 0.12),
                    )
                    return True
                gap_view_obj = self.device.find(index=-1, resourceIdMatches=containers_gap)
                containers_content_obj = self.device.find(resourceIdMatches=containers_content)

                if gap_view_obj.exists() and containers_content_obj.exists():
                    # Original logic when resource IDs exist
                    obj1 = gap_view_obj.get_bounds()["bottom"]
                    obj2 = (containers_content_obj.get_bounds()["bottom"] + containers_content_obj.get_bounds()["top"]) * 1 / 3
                    self.device.swipe_points(displayWidth / 2, obj1 - 5, displayWidth / 2, obj2 + 5)
                else:
                    # Fallback: simple scroll down from bottom to middle
                    logger.info("Using fallback scroll (resource IDs not found)")
                    start_y = displayHeight * 0.8  # Start from 80% down the screen
                    end_y = displayHeight * 0.3    # End at 30% down the screen
                    self.device.swipe_points(displayWidth / 2, start_y, displayWidth / 2, end_y)
            return True
        except Exception as e:
            logger.error(f"Error in swipe_to_fit_posts: {e}")
            return False
    def _find_likers_container(self):
        try:
            universal_actions = UniversalActions(self.device)
            containers_gap = safe_resource('GAP_VIEW_AND_FOOTER_SPACE')
            likes_view = self.device.find(index=-1, resourceId=safe_resource('ROW_FEED_TEXTVIEW_LIKES'), className=ClassName.TEXT_VIEW)
            
            likes_view_found = False

            if likes_view.exists():
                likes_view_found = True
            
            if not likes_view_found:
                logger.info("DEBUG: standard likes TextView not found. Checking for Clips like count...")
                clips_like_view = self.device.find(resourceIdMatches=case_insensitive_re('.*like_count.*'))
                if clips_like_view.exists():
                    likes_view = clips_like_view
                    likes_view_found = True
                    logger.info(f"DEBUG: Found likely like count via ID: '{likes_view.get_text()}' bounds={likes_view.get_bounds()}")

            if not likes_view_found:
                logger.info("DEBUG: standard likes TextView not found. Checking Buttons with digits...")
                for i in range(5):
                    btn = self.device.find(className=ClassName.BUTTON, textMatches=r"^\d+(?:[.,]\d+)?[kMB]?$", index=i)
                    if btn.exists():
                        try:
                            bounds = btn.get_bounds()
                            if bounds['top'] > 150 and bounds['bottom'] < 1160:
                                likes_view = btn
                                likes_view_found = True
                                logger.info(f"DEBUG: Found likely like count button: '{likes_view.get_text()}' bounds={bounds}")
                                break
                        except Exception:
                            pass
                    else:
                        break
            
            if not likes_view_found: 
                for i in range(5):
                    btn = self.device.find(className=ClassName.TEXT_VIEW, textMatches=r"^\d+(?:[.,]\d+)?[kMB]?$", index=i)
                    if btn.exists():
                        try:
                            bounds = btn.get_bounds()
                            if bounds['top'] > 150 and bounds['bottom'] < 1160:
                                likes_view = btn
                                likes_view_found = True
                                logger.info(f"DEBUG: Found likely like count TextView: '{likes_view.get_text()}' bounds={bounds}")
                                break
                        except Exception:
                            pass
                    else:
                        break

            if not likes_view_found: 
                logger.warning("DEBUG: No like count view found (TextView or Button).")
                return False, 0
                
            likes = self._get_number_of_likers(likes_view)
            return True, likes
        except Exception as e:
            logger.error(f"DEBUG: Exception in _find_likers_container: {e}")
            return False, 0

    def _get_number_of_likers(self, likes_view):
        try:
            if likes_view.exists():
                likes_view_text = likes_view.get_text()
                logger.info(f"DEBUG: Validating likes view text: '{likes_view_text}'")
                
                if not likes_view_text: return 0
                
                # Check 1: "Liked by X and others" -> standard feed
                # Normalize line breaks or spaces
                likes_view_text_clean = likes_view_text.replace("\n", " ").replace(",", "").replace(".", "")
                
                matches_likes = re.search(r"(?P<likes>\d+) (?:others|likes|personnes|autres)", likes_view_text_clean, re.IGNORECASE)
                if hasattr(matches_likes, "group"): 
                    val = int(matches_likes.group("likes"))
                    logger.info(f"DEBUG: Parsed likes (standard): {val}")
                    return val
                
                # Check 2: Just digits (Reels)
                if likes_view_text_clean.isdigit():
                    val = int(likes_view_text_clean)
                    logger.info(f"DEBUG: Parsed likes (digits): {val}")
                    return val

                # Check 3: "X likes"
                matches_simple = re.search(r"^(?P<likes>\d+)\s*(?:likes|j'aime)?$", likes_view_text_clean, re.IGNORECASE)
                if hasattr(matches_simple, "group"): 
                    val = int(matches_simple.group("likes"))
                    logger.info(f"DEBUG: Parsed likes (simple): {val}")
                    return val
                
                # Check 4: "Like number isX"
                matches_like_number = re.search(r"Like number is\s*(?P<likes>\d+)", likes_view_text_clean, re.IGNORECASE)
                if hasattr(matches_like_number, "group"): 
                    val = int(matches_like_number.group("likes"))
                    logger.info(f"DEBUG: Parsed likes (like number is): {val}")
                    return val
                
                logger.warning(f"DEBUG: Failed to parse likes from: {likes_view_text}")
            return 0
        except Exception as e: 
            logger.error(f"DEBUG: Exception in _get_number_of_likers: {e}")
            return 0
    def open_likers_container(self) -> bool:
        logger.info("Opening the likers container.")
        likes_view = self.device.find(index=-1, resourceId=safe_resource('ROW_FEED_TEXTVIEW_LIKES'), className=ClassName.TEXT_VIEW)
        if likes_view.exists():
            likes_view.click(Location.RIGHT)
            return True
        # IG >=412 exposes the like counter as a Button ("like_count") next to the media.
        likes_view = self.device.find(resourceIdMatches=case_insensitive_re('.*like_count.*'))
        if likes_view.exists():
            likes_view.click()
            return True
        # Fallback 1: TextView or Button with 'liked by', 'others', 'likes', 'j'aime'
        likes_txt = self.device.find(textMatches=case_insensitive_re(".*liked by.*|.*others.*|.*likes.*|.*j'aime.*"))
        if likes_txt.exists(Timeout.SHORT):
            likes_txt.click()
            return True
        # Fallback 2: Description containing 'view likes' or 'likes'
        likes_desc = self.device.find(descriptionMatches=case_insensitive_re(".*view likes.*|.*likes.*|.*j'aime.*"))
        if likes_desc.exists(Timeout.SHORT):
            likes_desc.click()
            return True
        logger.warning("Could not find anything to open the likers container with.")
        return False
    def _has_tags(self) -> bool:
        tags_icon = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('INDICATOR_ICON_VIEW')))
        self.has_tags = tags_icon.exists()
        return self.has_tags
    def _check_if_last_post(self, last_description, current_job) -> Tuple[bool, str, str, bool, bool, bool]:
        # SAFE: Always returns 6 values
        try:
            res = self._post_owner(current_job, Owner.GET_NAME)
            # Safe unpack
            username = res[0] if res and len(res) > 0 else None
            is_ad = res[1] if res and len(res) > 1 else False
            is_hashtag = res[2] if res and len(res) > 2 else False
            
            has_tags = self._has_tags()
            if not username: return False, "", "", False, False, has_tags
            post_description = self.device.find(index=-1, resourceIdMatches=safe_resource('ROW_FEED_TEXT'), textStartsWith=username)
            if post_description.exists():
                new_description = post_description.get_text().upper()
                if new_description != last_description: return False, new_description, username, is_ad, is_hashtag, has_tags
                return True, new_description, username, is_ad, is_hashtag, has_tags
            return False, "", username, is_ad, is_hashtag, has_tags
        except Exception as e:
            logger.error(f"Error checking last post: {e}")
            return False, "", "", False, False, False

    def _if_action_bar_is_over_obj_swipe(self, obj):
        action_bar_exists, _, action_bar_bottom = self._get_action_bar_position()
        if action_bar_exists:
            obj_top = obj.get_bounds()["top"]
            if action_bar_bottom > obj_top: UniversalActions(self.device)._swipe_points(direction=Direction.UP, delta_y=action_bar_bottom)
    def _get_action_bar_position(self) -> Tuple[bool, int, int]:
        action_bar = self.device.find(resourceIdMatches=safe_resource('ACTION_BAR_CONTAINER'))
        if action_bar.exists(): return (True, action_bar.get_bounds()["top"], action_bar.get_bounds()["bottom"])
        return False, 0, 0
    def _refresh_feed(self):
        refresh_pill = self.device.find(resourceId=safe_resource('NEW_FEED_PILL'))
        if refresh_pill.exists(Timeout.SHORT): refresh_pill.click()
        else: UniversalActions(self.device)._reload_page()
    def _check_if_ad_or_hashtag(self, post_owner_obj) -> Tuple[bool, bool, Optional[str]]:
        is_hashtag = False
        is_ad = False
        ad_reason = None
        owner_name = post_owner_obj.get_text() or ""
        ad_like_obj = post_owner_obj.sibling(resourceId=safe_resource('SECONDARY_LABEL'))
        if owner_name.startswith("#"): is_hashtag = True
        
        ad_keywords = ["sponsored", "sponsorisé", "patrocinado", "gesponsert", "sponsorizzato", "reklam", "ad", "publicité", "pub"]
        
        if ad_like_obj.exists():
            ad_like_txt = (ad_like_obj.get_text() or "").lower()
            matched = [k for k in ad_keywords if k in ad_like_txt]
            if matched:
                is_ad = True
                ad_reason = "branche1 secondary_label=%r mot_declencheur=%r" % (ad_like_txt, matched[0])

        # Fallback check for content-desc that might contain "Sponsored Reel" (e.g. hellofreshfrance dump)
        try:
            bounds = post_owner_obj.get_bounds()
            if not is_ad and bounds:
                # Basic check nearby items for 'sponsored' text/desc
                sponsored_node = self.device.find(textMatches=case_insensitive_re("Sponsored|Sponsorisé|Patrocinado|Ad|Publicité"))
                if sponsored_node.exists() and abs(sponsored_node.get_bounds()['top'] - bounds['top']) < 500:
                    is_ad = True
                    try:
                        _txt = sponsored_node.get_text()
                    except Exception:
                        _txt = "<texte illisible>"
                    ad_reason = "branche2 texte=%r delta_px=%s" % (
                        _txt, abs(sponsored_node.get_bounds()['top'] - bounds['top']))
        except:
            pass

        # ADDIAG : instrumentation temporaire. On ne change aucun comportement,
        # on note seulement QUELLE branche a decide "pub" et sur QUEL texte,
        # pour comprendre les 537 posts sur 563 ecartes le 05/09.
        if is_ad:
            logger.info("ADDIAG: owner=%r -> AD par %s" % (owner_name, ad_reason or "AUCUNE BRANCHE (anormal)"))

        return is_ad, is_hashtag, owner_name

    def get_text_from_screen(self, pt, obj) -> Optional[str]:
        return None

    def _post_owner(self, current_job, mode: Owner, username=None):
        # SAFE: Always returns correct tuple size
        is_ad = False
        is_hashtag = False
        try:
            post_owner_obj = None
            if username is None: 
                # Primary: resource ID
                post_owner_obj = self.device.find(resourceIdMatches=safe_resource('ROW_FEED_PHOTO_PROFILE_NAME'))
                
                if not post_owner_obj.exists():
                     post_owner_obj = self.device.find(resourceIdMatches=case_insensitive_re('.*clips_author_username.*'))
                
                if not post_owner_obj.exists():
                     logger.info("DEBUG: Profile Name ID not found. Trying fallbacks...")
                     
                     # Fallback 1: Sibling of Secondary Label (Location/Audio)
                     sec_label = self.device.find(resourceIdMatches=safe_resource('SECONDARY_LABEL'))
                     if sec_label.exists():
                         logger.info("DEBUG: Found Secondary Label. Checking siblings...")
                         for sibling in sec_label.sibling(className=ClassName.BUTTON): 
                             txt = sibling.get_text()
                             if txt and txt != sec_label.get_text():
                                 logger.info(f"DEBUG: SecLabel sibling candidate: {txt}")
                                 post_owner_obj = sibling
                                 break
                         if not post_owner_obj or not post_owner_obj.exists():
                             for sibling in sec_label.sibling(className=ClassName.TEXT_VIEW):
                                 txt = sibling.get_text()
                                 if txt and txt != sec_label.get_text():
                                     logger.info(f"DEBUG: SecLabel sibling TV candidate: {txt}")
                                     post_owner_obj = sibling
                                     break

                     # Fallback 2: "Follow" button text anchor
                     if not post_owner_obj or not post_owner_obj.exists():
                         follow_btn = self.device.find(textMatches=case_insensitive_re("Follow|Following|S'abonner|Abonné|Seguir|Folgen"))
                         if follow_btn.exists():
                             logger.info("DEBUG: Found Follow button. Checking siblings...")
                             for sibling in follow_btn.sibling(className=ClassName.TEXT_VIEW):
                                 txt = sibling.get_text()
                                 if txt and txt.lower() not in ["follow", "following", "s'abonner", "abonné", "seguir", "folgen", "•"]:
                                     post_owner_obj = sibling
                                     logger.info(f"DEBUG: Follow sibling candidate: {txt}")
                                     break
            
            else:
                post_owner_obj = self.device.find(resourceIdMatches=safe_resource('ROW_FEED_PHOTO_PROFILE_NAME'), textStartsWith=username)
                if not post_owner_obj.exists():
                    # IG >=412 renamed the author label; on Reels it is a Button.
                    post_owner_obj = self.device.find(resourceIdMatches=case_insensitive_re('.*clips_author_username.*'), textStartsWith=username)
                if not post_owner_obj.exists():
                    post_owner_obj = self.device.find(className=ClassName.BUTTON, textStartsWith=username)
                if not post_owner_obj.exists():
                    post_owner_obj = self.device.find(className=ClassName.TEXT_VIEW, textStartsWith=username)

            if post_owner_obj is None or not post_owner_obj.exists():
                logger.warning("DEBUG: Could not find post owner object.")
                if mode == Owner.GET_POSITION: return (None, False) 
                return (None, False, False) 

            if mode == Owner.OPEN:
                self._if_action_bar_is_over_obj_swipe(post_owner_obj)
                post_owner_obj.click()
                return (True, is_ad, is_hashtag)
            elif mode == Owner.GET_NAME:
                # Sponsored posts show up in every source, not just the feed, and
                # interacting with them wastes the session (and looks bot-like).
                check_result = self._check_if_ad_or_hashtag(post_owner_obj)
                if check_result: is_ad, is_hashtag, username = check_result
                else: is_ad, is_hashtag, username = False, False, None
                if is_ad:
                    logger.info("This post is an ad, skip.", extra={"color": f"{Fore.CYAN}"})
                if username is None:
                    raw_txt = post_owner_obj.get_text()
                    if raw_txt:
                        if " and " in raw_txt: username = raw_txt.split(" and ")[0]
                        else: username = raw_txt.replace("•", "").strip().split(" ", 1)[0]
                return (username, is_ad, is_hashtag)
            elif mode == Owner.GET_POSITION:
                return (post_owner_obj.get_bounds(), is_ad)
            
            return (None, is_ad, is_hashtag)
        except Exception as e:
            logger.error(f"Error in _post_owner: {e}")
            if mode == Owner.GET_POSITION: return (None, False)
            return (None, False, False)
    def _get_media_container(self):
        media = self.device.find(resourceIdMatches=safe_resource('CAROUSEL_AND_MEDIA_GROUP'))
        if not media.exists():
            media = self.device.find(resourceIdMatches=safe_resource('MEDIA_CONTAINER'))
        content_desc = media.get_desc() if media.exists() else None
        return media, content_desc
    @staticmethod
    def detect_media_type(content_desc) -> Tuple[Optional[MediaType], Optional[int]]:
        if content_desc is None: return None, None
        if re.match(r"^Photo|^Hidden Photo", content_desc, re.IGNORECASE): return MediaType.PHOTO, 1
        elif re.match(r"^Video|^Hidden Video", content_desc, re.IGNORECASE): return MediaType.VIDEO, 1
        elif re.match(r"^IGTV", content_desc, re.IGNORECASE): return MediaType.IGTV, 1
        elif re.match(r"^Reel", content_desc, re.IGNORECASE): return MediaType.REEL, 1
        return MediaType.UNKNOWN, 1
    def _like_in_post_view(self, mode: LikeMode, skip_media_check: bool = False, already_watched: bool = False):
        if skip_media_check: return
        media, content_desc = self._get_media_container()
        
        if mode == LikeMode.DOUBLE_CLICK and media.exists():
            # double_click is a View-level method (it picks a random padded
            # point within the element's own bounds) — call it on the media
            # element we already found, not on the device facade itself.
            media.double_click()
            logger.info("Double clicked media to like post.")
            return

        # SINGLE_CLICK or fallback
        like_btn = self.device.find(resourceIdMatches=safe_resource('ROW_FEED_BUTTON_LIKE'))
        if not like_btn.exists():
            like_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('CLIPS_LIKE_BUTTON')))
        if not like_btn.exists():
            like_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('TOOLBAR_LIKE_BUTTON')))
        if not like_btn.exists():
            like_btn = self.device.find(descriptionMatches=case_insensitive_re(Tab.LIKE))

        if like_btn.exists():
            like_btn.click()
            logger.info("Like button clicked successfully")
        else:
            logger.warning("Could not find like button for this post")
    def _follow_in_post_view(self):
        self.device.find(resourceIdMatches=safe_resource('BUTTON')).click()
    def _comment_in_post_view(self):
        # Try resource ID first
        comment_btn = self.device.find(resourceIdMatches=safe_resource('ROW_FEED_BUTTON_COMMENT'))
        
        if not comment_btn.exists():
            comment_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('CLIPS_COMMENT_BUTTON')))
            
        # Fallback using ContentDescription
        if not comment_btn.exists():
            comment_btn = self.device.find(descriptionMatches=case_insensitive_re(Tab.COMMENT))
        
        if comment_btn.exists():
            comment_btn.click()
            logger.info("Comment button clicked successfully")
            return True
        else:
            logger.warning("Could not find comment button")
            return False

    def _check_if_liked(self):
        # Try to find like button by resource ID first
        bnt_like_obj = self.device.find(resourceIdMatches=safe_resource('ROW_FEED_BUTTON_LIKE'))
        
        # Fallback: Clips Like button
        if not bnt_like_obj.exists():
            bnt_like_obj = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('CLIPS_LIKE_BUTTON')))

        # Fallback: Content Description
        if not bnt_like_obj.exists():
             bnt_like_obj = self.device.find(descriptionMatches=case_insensitive_re(Tab.LIKE + Tab.UNLIKE))

        if bnt_like_obj.exists():
            desc = bnt_like_obj.get_desc()
            # If description contains "Unlike" or "Liked" (captured in UNLIKE list or heuristics)
            # OR if it is selected
            if bnt_like_obj.get_selected():
                return True
            
            # Text based check from UNLIKE list
            if desc:
                for unlike_text in Tab.UNLIKE:
                    if unlike_text.lower() in desc.lower():
                        return True
                if "liked" in desc.lower(): # Fallback for English "Liked" if not in list
                    return True
                    
        return False


class ProfileView:
    def __init__(self, device: DeviceFacade, is_own_profile=False):
        self.device = device
        self.is_own_profile = is_own_profile

    def click_on_avatar(self) -> bool:
        tab_avatar = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('TAB_AVATAR')))
        if tab_avatar.exists():
            tab_avatar.click()
            return True
        profile_tab = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('PROFILE_TAB')))
        if profile_tab.exists():
            profile_tab.click()
            return True
        return False

    def navigateToOptions(self):
        self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('MENU_SETTINGS_ROW'))).click()

    def StoryRing(self):
        """The ring drawn around the avatar when the account has an active story."""
        ring = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('REEL_RING')))
        if ring.exists():
            return ring
        # Fallback: the avatar itself announces the story through its description.
        return self.device.find(
            resourceIdMatches=case_insensitive_re(safe_resource('ROW_PROFILE_HEADER_IMAGEVIEW')),
            descriptionMatches=case_insensitive_re(".*story.*"),
        )

    def live_marker(self):
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('LIVE_BADGE_VIEW')))

    def count_photo_in_view(self) -> Tuple[int, int]:
        """Return (complete rows fully on screen, posts in the trailing partial row)."""
        cells = []
        try:
            for cell in self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('IMAGE_BUTTON'))):
                try:
                    b = cell.get_bounds()
                except Exception:
                    continue
                cells.append((b["top"], b["bottom"] - b["top"]))
        except Exception as e:
            logger.debug(f"Could not enumerate the post grid: {e}")
            return 0, 0
        if not cells:
            return 0, 0
        # A row clipped by the screen edge reports a smaller height than a whole one.
        full_height = Counter(h for _, h in cells).most_common(1)[0][0]
        rows = {}
        for top, h in cells:
            if h < full_height:
                continue
            rows[top] = rows.get(top, 0) + 1
        if not rows:
            return 0, 0
        ordered = [rows[top] for top in sorted(rows)]
        full_rows = sum(1 for count in ordered if count >= 3)
        trailing = next((count for count in ordered if count < 3), 0)
        return full_rows, trailing

    def getSomeText(self, resource_id=None):
        return self._getSomeText(resource_id)
    def _getSomeText(self, resource_id=None):
        if not resource_id: return None
        view = self.device.find(resourceIdMatches=case_insensitive_re(resource_id))
        if view.exists(Timeout.SHORT): return view.get_text()
        return None
    def getUsername(self):
        try:
            view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ACTION_BAR_TITLE')))
            if view.exists(): return view.get_text()
        except Exception as e:
            logger.debug(f"Error getting username from action bar: {e}")

        try:
            view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_PROFILE_HEADER_TEXTVIEW_USERNAME')))
            if view.exists(): return view.get_text()
        except Exception as e:
            logger.debug(f"Error getting username from profile header: {e}")
            
        return None
    def _parse_profile_count(self, text):
        if not text:
            return 0
        text = text.upper().replace(',', '').replace(' ', '').replace('\n', '')
        # Check for K or M multipliers
        multiplier = 1
        if 'K' in text:
            multiplier = 1000
        elif 'M' in text:
            multiplier = 1000000
        
        # Extract numeric part (including decimals like 1.5)
        import re
        match = re.search(r'([0-9\.]+)', text)
        if match:
            try:
                return int(float(match.group(1)) * multiplier)
            except ValueError:
                return 0
        return 0

    def getPostsCount(self):
        text = self.getSomeText(safe_resource('ROW_PROFILE_HEADER_TEXTVIEW_POST_COUNT'))
        if not text:
            text = self.getSomeText('.*profile_header_familiar_post_count_value.*')
        return self._parse_profile_count(text)
        
    def getFollowersCount(self):
        text = self.getSomeText(safe_resource('ROW_PROFILE_HEADER_TEXTVIEW_FOLLOWERS_COUNT'))
        if not text:
            text = self.getSomeText('.*profile_header_familiar_followers_value.*')
        if not text:
            elem = self.device.find(descriptionMatches=case_insensitive_re('.*followers.*'))
            if elem.exists(Timeout.SHORT):
                text = elem.get_desc()
        return self._parse_profile_count(text)
        
    def getFollowingCount(self):
        text = self.getSomeText(safe_resource('ROW_PROFILE_HEADER_TEXTVIEW_FOLLOWING_COUNT'))
        if not text:
            text = self.getSomeText('.*profile_header_familiar_following_value.*')
        if not text:
            elem = self.device.find(descriptionMatches=case_insensitive_re('.*following.*'))
            if elem.exists(Timeout.SHORT):
                text = elem.get_desc()
        return self._parse_profile_count(text)
    def getProfileInfo(self):
        try:
            username = self.getUsername()
            posts = self.getPostsCount()
            followers = self.getFollowersCount()
            following = self.getFollowingCount()
            return username, posts, followers, following
        except Exception as e:
            logger.error(f"Error getting profile info: {e}")
            return None, 0, 0, 0

    def getMutualFriends(self):
        view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('PROFILE_HEADER_FOLLOW_CONTEXT_TEXT')))
        if view.exists():
            return 0 # Parsing logic can be added later if needed
        return 0

    def getLinkInBio(self):
        view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('PROFILE_HEADER_WEBSITE')))
        if view.exists(): return view.get_text()
        return None

    def getFullName(self):
        view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('PROFILE_HEADER_FULL_NAME')))
        if view.exists(): return view.get_text()
        return ""

    def getProfileBiography(self):
        view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('PROFILE_HEADER_BIO_TEXT')))
        if getattr(view, 'exists', lambda: False)() and view.exists():
            return view.get_text()
            
        # Fallback for newer Instagram versions where bio text has no ID or is 'ig_text'
        try:
            ignore_texts = ['message', 'follow', 'following', 'requested', 'contact', 'email', 'see translation']
            bio_text = ""
            for node in self.device.deviceV2(className="android.widget.TextView"):
                if not node.exists: continue
                rid = node.info.get('resourceName', '')
                text = node.info.get('text', '')
                if text and (not rid or 'ig_text' in rid):
                    if text.lower() not in ignore_texts and len(text) > 2:
                        bio_text += " " + text
            return bio_text.strip()
        except Exception as e:
            logger.debug(f"Error checking fallback profile biography: {e}")
            
        return ""

    def getFollowButton(self):
        return None, "Unknown"

    def isPrivateAccount(self):
        view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('PRIVATE_PROFILE_EMPTY_STATE')))
        if view.exists(Timeout.SHORT):
            return True
        text_view = self.device.find(textMatches=case_insensitive_re(r".*This account is private.*|.*Ce compte est privé.*|.*Esta cuenta es privada.*|.*Esta conta é privada.*|.*Este perfil é privado.*"))
        return text_view.exists(Timeout.SHORT)
        
    def navigateToFollowers(self):
        logger.info("Navigate to followers.")
        followers_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_PROFILE_HEADER_FOLLOWERS_CONTAINER')))
        if followers_btn.exists():
            followers_btn.click()
            return True
            
        followers_regex = r".*followers.*|.*abonnés.*|.*seguidores.*"
        followers_btn = self.device.find(textMatches=case_insensitive_re(followers_regex))
        if followers_btn.exists():
            try:
                followers_btn.parent().click()
                return True
            except Exception:
                followers_btn.click()
                return True
            
        followers_btn = self.device.find(descriptionMatches=case_insensitive_re(followers_regex))
        if followers_btn.exists():
            try:
                followers_btn.parent().click()
                return True
            except Exception:
                followers_btn.click()
                return True
            
        logger.warning("Followers container not found.")
        return False
        
    def navigateToFollowing(self):
        logger.info("Navigate to following.")
        following_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_PROFILE_HEADER_FOLLOWING_CONTAINER')))
        if following_btn.exists():
            following_btn.click()
            return True
            
        following_regex = r".*following.*|.*abonnements.*|.*seguindo.*|.*segui.*"
        following_btn = self.device.find(textMatches=case_insensitive_re(following_regex))
        if following_btn.exists():
            try:
                following_btn.parent().click()
                return True
            except Exception:
                following_btn.click()
                return True
            
        following_btn = self.device.find(descriptionMatches=case_insensitive_re(following_regex))
        if following_btn.exists():
            try:
                following_btn.parent().click()
                return True
            except Exception:
                following_btn.click()
                return True
            
        logger.warning("Following container not found.")
        return False

    def swipe_to_fit_posts(self):
        """Scroll down on profile to fit posts grid into view"""
        try:
            universal_actions = UniversalActions(self.device)
            universal_actions._swipe_points(direction=Direction.DOWN, delta_y=randint(300, 450))
            return 350
        except Exception as e:
            logger.error(f"Error in ProfileView.swipe_to_fit_posts: {e}")
            return 0

class AccountView:
    def __init__(self, device: DeviceFacade, is_own_profile=False):
        self.device = device
        self.is_own_profile = is_own_profile
    def navigate_to_main_account(self):
        # This runs once at session start. If the app wasn't force-closed since
        # the last run (e.g. Instagram is still foregrounded from a previous
        # session or was left mid-navigation by a crash), it can be sitting
        # anywhere — a random opened post, a followers list, several screens
        # deep. Being generous with back-presses here (a one-time cost at
        # startup, not per-interaction) is what actually gets us to a known,
        # clean state before we trust anything we read off the screen.
        tab_bar_view = TabBarView(self.device)
        if not tab_bar_view._getTabBar().exists(Timeout.SHORT):
            logger.debug("Not on a main tab at session start, backing out to one.")
            for _ in range(8):
                if tab_bar_view._getTabBar().exists(Timeout.SHORT):
                    break
                self.device.back()
                random_sleep(0.5, 1, modulable=False)
        tab_bar_view.navigateToProfile()

    def refresh_account(self):
        logger.info("Refreshing account...")
        UniversalActions(self.device)._reload_page()

    def changeToUsername(self, username):
        logger.info(f"Changing to {username}...")
        # Don't trust whatever happens to be on screen — force a fresh navigation
        # to our own profile tab before reading the username. Reading it as-is can
        # pick up someone else's profile if we were left mid-navigation (e.g. deep
        # in a followers list), which would make the bot think it's logged in as
        # that other person and interact as them.
        TabBarView(self.device).navigateToProfile()
        current = ProfileView(self.device).getUsername()
        if current == username:
            logger.info("Already on correct account.")
            return True
        # One retry: the header can take a beat to finish rendering after navigation.
        random_sleep(1, 2, modulable=False)
        current = ProfileView(self.device).getUsername()
        if current == username:
            logger.info("Already on correct account.")
            return True
        # This bot has no real multi-account switching implemented. Proceeding
        # while logged in as the wrong account would mean posting real likes/
        # comments/follows under someone else's identity — abort instead.
        logger.error(
            f"Expected to be logged in as @{username} but the app shows "
            f"@{current}. Multi-account switching isn't implemented — aborting "
            f"this session instead of risking interactions on the wrong account."
        )
        return False

    def navigateToOptions(self):
        self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('MENU_SETTINGS_ROW'))).click()
    def getFollowersCount(self):
        followers_view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_PROFILE_HEADER_TEXTVIEW_FOLLOWERS_COUNT')))
        if followers_view.exists(): return get_value(followers_view.get_text(), "Followers count: ", 0)
        return 0
    def getFollowingCount(self):
        following_view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_PROFILE_HEADER_TEXTVIEW_FOLLOWING_COUNT')))
        if following_view.exists(): return get_value(following_view.get_text(), "Following count: ", 0)
        return 0

class CurrentStoryView:
    def __init__(self, device: DeviceFacade):
        self.device = device
    def getStoryFrame(self):
        frame = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('REEL_VIEWER_MEDIA_CONTAINER')))
        if frame.exists():
            return frame
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('REEL_VIEWER_IMAGE_VIEW')))
    def getUsernameLabel(self):
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('REEL_VIEWER_TITLE')), className=ClassName.TEXT_VIEW)
    def getUsername(self) -> str:
        # The story can advance between the lookup and the read, which makes the
        # element vanish mid-call; report it as unknown rather than blowing up.
        try:
            label = self.getUsernameLabel()
            if not label.exists():
                return "BUG!"
            return label.get_text() or "BUG!"
        except Exception:
            return "BUG!"

class OpenedPostView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def watch_media(self, media_type: MediaType):
        random_sleep(2, 4)

    def _is_post_liked(self):
        """
        Check if the current opened post is liked.
        Returns a tuple (is_liked, is_video)
        """
        logger.info("Checking if post is liked...")
        # Try to find the like button (Standard Feed or Reels)
        like_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_FEED_BUTTON_LIKE')))
        if not like_btn.exists():
            like_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('TOOLBAR_LIKE_BUTTON')))
        if not like_btn.exists():
            like_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('CLIPS_LIKE_BUTTON')))
        
        if like_btn.exists():
            desc = (like_btn.get_desc() or "").lower()
            selected = like_btn.get_selected()
            logger.info(f"Like button found. Desc: '{like_btn.get_desc()}', Selected: {selected}")
            
            # Instagram sets content-desc to 'Unlike', 'Liked', 'Je n'aime plus', etc. when already liked
            if selected or any(w in desc for w in ["unlike", "liked", "aimé", "n'aime plus"]):
                return True, False 
            return False, False
            
        logger.warning("Like button NOT found!")
        return False, False

    def like_post(self):
        logger.info("Liking post...")
        like_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('ROW_FEED_BUTTON_LIKE')))
        if not like_btn.exists():
            like_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('TOOLBAR_LIKE_BUTTON')))
        if not like_btn.exists():
            like_btn = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('CLIPS_LIKE_BUTTON')))
        
        if like_btn.exists():
            like_btn.click()
            return True
        logger.warning("Like button NOT found!")
        return False

    def like_video(self):
        return self.like_post()

    def open_video(self) -> bool:
        """Make sure the video/reel player is actually on screen before watching it."""
        video = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('VIDEO_CONTAINER_AND_CLIPS_VIDEO_CONTAINER')))
        if video.exists(Timeout.MEDIUM):
            return True
        # Some reels only expose the media component wrapper.
        media = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('MEDIA_CONTAINER')))
        if media.exists(Timeout.SHORT):
            return True
        logger.warning("Video player did not open.")
        return False

    def start_video(self):
        """
        Interacts with video container to ensure it plays
        """
        video = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('VIDEO_CONTAINER')))
        if video.exists():
            video.click()

    def _getListViewLikers(self):
        # IG >=412 renders the likers sheet as a RecyclerView (same "android:id/list"
        # resource id, different class) — a ListView-only match finds nothing to
        # scroll and blows up with UiObjectNotFoundError.
        view = self.device.find(resourceIdMatches=safe_resource('LIST'), className=ClassName.LIST_VIEW)
        if view.exists():
            return view
        return self.device.find(resourceIdMatches=safe_resource('LIST'))

    def _getUserContainer(self):
        return self.device.find(resourceIdMatches=safe_resource('USER_LIST_CONTAINER'))

    def _getUserName(self, item):
        return item.child(resourceIdMatches=safe_resource('ROW_USER_PRIMARY_NAME'))

class PostsGridView:
    def __init__(self, device: DeviceFacade):
        self.device = device
    @staticmethod
    def _media_from_description(desc: str) -> Tuple[MediaType, int]:
        """Read the grid cell description, e.g. '2 photos and 7 videos by X at row 1, column 2'."""
        if not desc:
            return MediaType.UNKNOWN, 1
        mixed = re.match(r"^(\d+)\s+photos?\s+and\s+(\d+)\s+videos?", desc, re.IGNORECASE)
        if mixed:
            return MediaType.CAROUSEL, int(mixed.group(1)) + int(mixed.group(2))
        several = re.match(r"^(\d+)\s+(photos|videos)", desc, re.IGNORECASE)
        if several and int(several.group(1)) > 1:
            return MediaType.CAROUSEL, int(several.group(1))
        if re.match(r"^Reel", desc, re.IGNORECASE):
            return MediaType.REEL, 1
        if re.match(r"^IGTV", desc, re.IGNORECASE):
            return MediaType.IGTV, 1
        if re.match(r"^Video", desc, re.IGNORECASE):
            return MediaType.VIDEO, 1
        if re.match(r"^Photo", desc, re.IGNORECASE):
            return MediaType.PHOTO, 1
        return MediaType.UNKNOWN, 1

    def _enumerate_grid_cells(self):
        cells = []
        try:
            for cell in self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('IMAGE_BUTTON'))):
                try:
                    b = cell.get_bounds()
                except Exception:
                    continue
                cells.append((b["top"], b["left"], cell))
        except Exception as e:
            logger.debug(f"Could not enumerate the post grid: {e}")
            return []
        cells.sort(key=lambda c: (c[0], c[1]))
        return cells

    def has_repeated_posts(self, min_repeats=3) -> bool:
        """
        Detect spam/fake profiles that post the exact same image over and over
        (seen as far as 6-8 times in a row). Compares downscaled thumbnails from
        a single screenshot of the grid rather than opening every post.
        """
        cells = self._enumerate_grid_cells()
        if len(cells) < min_repeats:
            return False
        screenshot_path = f"temp_grid_check_{randint(0, 999999)}.png"
        try:
            self.device.deviceV2.screenshot(screenshot_path)
            img = Image.open(screenshot_path).convert("RGB")
        except Exception as e:
            logger.debug(f"Could not screenshot the grid for a repost check: {e}")
            return False
        finally:
            try:
                os.remove(screenshot_path)
            except Exception:
                pass

        hash_counts = {}
        for top, left, cell in cells:
            try:
                bounds = cell.get_bounds()
                box = (bounds["left"], bounds["top"], bounds["right"], bounds["bottom"])
                thumb = img.crop(box).resize((16, 16)).convert("L")
                digest = hashlib.md5(thumb.tobytes()).hexdigest()
            except Exception:
                continue
            hash_counts[digest] = hash_counts.get(digest, 0) + 1

        worst = max(hash_counts.values(), default=0)
        if worst >= min_repeats:
            logger.warning(
                f"This profile reposts the same image {worst} times in the visible "
                "grid — looks like a spam/fake account. Skipping likes here."
            )
            return True
        return False

    def navigateToPost(self, row, col):
        # The grid is a flat list of cells laid out 3 per row; address them in
        # reading order rather than through a container index (which moved in IG 412).
        # After returning from a post, IG re-renders this grid row by row rather
        # than all at once — reading it right away often only sees the first row.
        # Retry for a couple seconds instead of failing the moment our target
        # row hasn't been painted yet.
        index = row * 3 + col
        cells = self._enumerate_grid_cells()
        for _ in range(6):
            if len(cells) > index:
                break
            random_sleep(0.5, 1, modulable=False)
            cells = self._enumerate_grid_cells()

        if not cells:
            logger.warning("No post found in the grid.")
            return None, MediaType.UNKNOWN, 0
        if index >= len(cells):
            logger.warning(f"Post at row {row + 1}, column {col + 1} is not on screen.")
            return None, MediaType.UNKNOWN, 0

        target = cells[index][2]
        try:
            desc = target.get_desc() or ""
        except Exception:
            desc = ""
        media_type, obj_count = self._media_from_description(desc)
        target.click()
        random_sleep(0.5, 1, modulable=False)
        # A stale/mistimed tap can land without Instagram ever transitioning
        # off the grid. Blindly returning OpenedPostView() here regardless
        # made callers believe a post opened and go on to scroll/inspect the
        # still-visible grid forever — there is no post-row/like-count data
        # there to find, so it just spun in place indefinitely.
        grid_marker = self.device.find(
            resourceIdMatches=case_insensitive_re(safe_resource('MEDIA_SET_ROW_CONTENT_IDENTIFIER'))
        )
        if grid_marker.exists(Timeout.SHORT):
            logger.warning(
                f"Clicking the post at row {row + 1}, column {col + 1} didn't open it."
            )
            return None, MediaType.UNKNOWN, 0
        return OpenedPostView(self.device), media_type, obj_count

    def _get_post_view(self):
        """A view that only exists once the profile's post grid has actually rendered."""
        grid = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('MEDIA_SET_ROW_CONTENT_IDENTIFIER')))
        # The header/tabs paint before the grid rows do. An instant (no-wait) check
        # here loses that race almost every time and falls through to the tabs-only
        # signal below, which is satisfied before any post cell exists — the very
        # next navigateToPost() call then finds nothing. Give the grid a real beat.
        if grid.exists(Timeout.MEDIUM):
            return grid
        # Profiles with no posts still show the tab strip, so callers don't loop forever.
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('PROFILE_TABS_CONTAINER')))

class LanguageView:
    def __init__(self, device: DeviceFacade):
        self.device = device
    def setLanguage(self, language: str):
        search_edit_text = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('SEARCH')))
        search_edit_text.set_text(language)
        list_view = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('LANGUAGE_LIST_LOCALE')), className=ClassName.LISTVIEW)
        first_item = list_view.child(index=0)
        first_item.click()

class FollowingView(AccountView):
    def __init__(self, device: DeviceFacade):
        super().__init__(device)
    def scrollDown(self):
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('FOLLOW_LIST_CONTAINER'))).scroll(Direction.DOWN)

    def do_unfollow_from_list(self, username=None, user_row=None) -> bool:
        """Unfollow straight from a follow list row, without opening the profile."""
        button = None
        if user_row is not None:
            button = user_row.child(
                resourceIdMatches=case_insensitive_re(safe_resource('ROW_FOLLOW_BUTTON')),
                textMatches=case_insensitive_re("^Following|^Requested"),
            )
            if not button.exists():
                button = user_row.child(textMatches=case_insensitive_re("^Following|^Requested"))
        if button is None or not button.exists():
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_TEXTVIEW_REGEX,
                clickable=True,
                textMatches=case_insensitive_re("^Following|^Requested"),
            )
        if not button.exists():
            logger.error(f"Cannot find the Following button for @{username}.")
            return False

        button.click()
        logger.info(f"Unfollow @{username}.", extra={"color": f"{Fore.YELLOW}"})

        # Instagram asks to confirm, either in a bottom sheet or a plain dialog.
        confirm = self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('FOLLOW_SHEET_UNFOLLOW_ROW')))
        if confirm.exists(Timeout.MEDIUM):
            confirm.click()
        else:
            confirm = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_TEXTVIEW_REGEX,
                textMatches=case_insensitive_re("^Unfollow"),
            )
            if confirm.exists(Timeout.SHORT):
                confirm.click()
            else:
                logger.warning(f"No unfollow confirmation appeared for @{username}.")
                return False
        return True

class FollowersView(AccountView):
    def __init__(self, device: DeviceFacade):
        super().__init__(device)
    def scrollDown(self):
        return self.device.find(resourceIdMatches=case_insensitive_re(safe_resource('FOLLOW_LIST_CONTAINER'))).scroll(Direction.DOWN)
