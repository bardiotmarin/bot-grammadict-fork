import logging
import os
from datetime import datetime, timedelta
from enum import Enum, unique

from colorama import Fore

from GramAddict.core.decorators import run_safely
from GramAddict.core.device_facade import DeviceFacade, Timeout
from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.resources import ClassName
from GramAddict.core.resources import ResourceID as resources
from GramAddict.core.scroll_end_detector import ScrollEndDetector
from GramAddict.core.storage import FollowingStatus
from GramAddict.core.utils import (
    get_value,
    inspect_current_view,
    random_sleep,
    save_crash,
)
from GramAddict.core.views import (
    Direction,
    FollowingView,
    ProfileView,
    UniversalActions,
)

logger = logging.getLogger(__name__)

FOLLOWING_REGEX = "^Following|^Requested"
UNFOLLOW_REGEX = "^Unfollow"
LEAST_INTERACTED_COOLDOWN_HOURS = 24


class ActionUnfollowLeastInteracted(Plugin):
    """Handles the functionality of unfollowing least interacted accounts"""

    def __init__(self):
        super().__init__()
        self.description = "Handles the functionality of unfollowing least interacted accounts"
        self.arguments = [
            {
                "arg": "--unfollow-least-interacted",
                "nargs": None,
                "help": "unfollow at most given number of users from the 'Least interacted with' category. Only runs once every 24 hours. It can be a number (e.g. 10) or a range (e.g. 10-20)",
                "metavar": "10-20",
                "default": None,
                "operation": True,
            },
        ]

    def run(self, device, configs, storage, sessions, profile_filter, plugin):
        class State:
            def __init__(self):
                pass

            unfollowed_count = 0
            is_job_completed = False

        self.args = configs.args
        self.device_id = configs.args.device
        self.state = State()
        self.session_state = sessions[-1]
        self.sessions = sessions
        self.unfollow_type = plugin
        self.ResourceID = resources(self.args.app_id)

        # Check 24-hour cooldown
        if not self._can_run_least_interacted(storage):
            logger.info(
                "Least interacted unfollow job was already run in the last 24 hours. Skip.",
                extra={"color": f"{Fore.YELLOW}"},
            )
            return

        count_arg = get_value(
            getattr(self.args, self.unfollow_type.replace("-", "_")),
            "Unfollow least interacted count: {}",
            10,
        )

        count = min(
            count_arg,
            self.session_state.my_following_count - int(self.args.min_following),
        )
        if count < 1:
            logger.warning(
                f"Now you're following {self.session_state.my_following_count} accounts, {'less then' if count <0 else 'equal to'} min following allowed (you set min-following: {self.args.min_following}). No further unfollows are required. Finish."
            )
            return
        elif self.session_state.my_following_count < count_arg:
            logger.warning(
                f"You can't unfollow {count_arg} accounts, because you are following {self.session_state.my_following_count} accounts. For that reason only {count} unfollows can be performed."
            )
        elif count < count_arg:
            logger.warning(
                f"You can't unfollow {count_arg} accounts, because you set min-following to {self.args.min_following} and you have {self.session_state.my_following_count} followers. For that reason only {count} unfollows can be performed."
            )

        @run_safely(
            device=device,
            device_id=self.device_id,
            sessions=self.sessions,
            session_state=self.session_state,
            screen_record=self.args.screen_record,
            configs=configs,
        )
        def job():
            self.unfollow_least_interacted(
                device,
                count - self.state.unfollowed_count,
                self.on_unfollow,
                storage,
                self.session_state.my_username,
                plugin,
            )
            logger.info(
                f"Unfollowed {self.state.unfollowed_count} least interacted accounts, finish.",
                extra={"color": f"{Fore.CYAN}"},
            )
            self.state.is_job_completed = True

            # Mark the job as completed in storage
            self._mark_least_interacted_completed(storage)
            device.back()

        while not self.state.is_job_completed and (self.state.unfollowed_count < count):
            job()

    def _can_run_least_interacted(self, storage) -> bool:
        """Check if least interacted job can run (24-hour cooldown)"""
        cooldown_file = os.path.join(storage.account_path, "least_interacted_last_run.txt")

        if not os.path.exists(cooldown_file):
            return True

        try:
            with open(cooldown_file, "r") as f:
                last_run_str = f.read().strip()
                last_run = datetime.fromisoformat(last_run_str)

            time_diff = datetime.now() - last_run
            hours_since_last_run = time_diff.total_seconds() / 3600

            if hours_since_last_run >= LEAST_INTERACTED_COOLDOWN_HOURS:
                logger.info(
                    f"Last least interacted run was {hours_since_last_run:.1f} hours ago. Can run again.",
                    extra={"color": f"{Fore.GREEN}"},
                )
                return True
            else:
                hours_remaining = LEAST_INTERACTED_COOLDOWN_HOURS - hours_since_last_run
                logger.info(
                    f"Need to wait {hours_remaining:.1f} more hours before running least interacted unfollow again.",
                    extra={"color": f"{Fore.YELLOW}"},
                )
                return False
        except Exception as e:
            logger.error(f"Error reading cooldown file: {e}. Allowing run.")
            return True

    def _mark_least_interacted_completed(self, storage):
        """Mark the least interacted job as completed"""
        cooldown_file = os.path.join(storage.account_path, "least_interacted_last_run.txt")

        try:
            with open(cooldown_file, "w") as f:
                f.write(datetime.now().isoformat())
            logger.debug("Marked least interacted job as completed.")
        except Exception as e:
            logger.error(f"Error writing cooldown file: {e}")

    def unfollow_least_interacted(
        self,
        device,
        count,
        on_unfollow,
        storage,
        my_username,
        job_name,
    ):
        skipped_list_limit = get_value(self.args.skipped_list_limit, None, 15)
        skipped_fling_limit = get_value(self.args.fling_when_skipped, None, 0)
        posts_end_detector = ScrollEndDetector(
            repeats_to_end=2,
            skipped_list_limit=skipped_list_limit,
            skipped_fling_limit=skipped_fling_limit,
        )

        ProfileView(device).navigateToFollowing()

        # Navigate to Categories and select "Least interacted with"
        if not self._navigate_to_least_interacted_category(device):
            logger.error("Could not navigate to 'Least interacted with' category. Finish.")
            return

        self.iterate_over_least_interacted(
            device,
            count,
            on_unfollow,
            storage,
            my_username,
            posts_end_detector,
            job_name,
        )

    def _navigate_to_least_interacted_category(self, device) -> bool:
        """Navigate to the 'Least interacted with' category"""
        logger.info("Looking for 'Least interacted with' category on the following page.")

        # Wait for the following page to load
        random_sleep(2, 3)

        # Use the exact resource ID and text from Appium Inspector
        least_interacted_option = device.find(
            resourceId="com.instagram.android:id/title",
            text="Least interacted with"
        )

        if not least_interacted_option.exists(Timeout.MEDIUM):
            logger.error("Cannot find 'Least interacted with' category on the following page.")
            logger.info("Make sure you have accounts in the 'Least interacted with' category.")
            return False

        logger.info("Found 'Least interacted with' category, clicking it.")
        least_interacted_option.click()
        random_sleep(3, 5)  # Wait for the list to load

        # Verify we're now in the least interacted list by checking if user list is loaded
        user_list = device.find(
            resourceIdMatches=self.ResourceID.USER_LIST_CONTAINER,
        )
        if not user_list.exists(Timeout.LONG):
            logger.error("Could not load the least interacted accounts list.")
            return False

        logger.info("Successfully loaded least interacted accounts list.")
        return True

    def on_unfollow(self):
        self.state.unfollowed_count += 1
        self.session_state.totalUnfollowed += 1

    def iterate_over_least_interacted(
        self,
        device,
        count,
        on_unfollow,
        storage,
        my_username,
        posts_end_detector,
        job_name,
    ):
        """Iterate over the least interacted accounts and unfollow them"""
        # Wait until list is rendered
        user_lst = device.find(
            resourceId=self.ResourceID.FOLLOW_LIST_CONTAINER,
            className=ClassName.LINEAR_LAYOUT,
        )
        user_lst.wait(Timeout.LONG)

        checked = {}
        unfollowed_count = 0
        total_unfollows_limit_reached = False
        posts_end_detector.notify_new_page()
        prev_screen_iterated_followings = []

        while True:
            screen_iterated_followings = []
            logger.info("Iterate over visible least interacted accounts.")

            user_list = device.find(
                resourceIdMatches=self.ResourceID.USER_LIST_CONTAINER,
            )
            row_height, n_users = inspect_current_view(user_list)

            for item in user_list:
                cur_row_height = item.get_height()
                if cur_row_height < row_height:
                    continue

                user_info_view = item.child(index=1)
                user_name_view = user_info_view.child(index=0).child()
                if not user_name_view.exists():
                    logger.info(
                        "Next item not found: probably reached end of the screen.",
                        extra={"color": f"{Fore.GREEN}"},
                    )
                    break

                username = user_name_view.get_text()
                screen_iterated_followings.append(username)

                if username not in checked:
                    checked[username] = None

                    # Check whitelist protection
                    if storage.is_user_in_whitelist(username):
                        logger.info(f"@{username} is in whitelist. Skip.")
                        continue

                    # Unfollow directly from the list (like the other unfollow jobs)
                    unfollowed = FollowingView(device).do_unfollow_from_list(
                        user_row=item, username=username
                    )

                    if unfollowed:
                        storage.add_interacted_user(
                            username,
                            self.session_state.id,
                            unfollowed=True,
                            job_name=job_name,
                            target="least-interacted",
                        )
                        on_unfollow()
                        unfollowed_count += 1
                        total_unfollows_limit_reached = self.session_state.check_limit(
                            limit_type=self.session_state.Limit.UNFOLLOWS,
                            output=True,
                        )

                    if unfollowed_count >= count or total_unfollows_limit_reached:
                        return
                else:
                    logger.debug(f"Already checked {username}.")

            # Handle scrolling and end detection
            if screen_iterated_followings != prev_screen_iterated_followings:
                prev_screen_iterated_followings = screen_iterated_followings
                logger.info("Need to scroll now.", extra={"color": f"{Fore.GREEN}"})

                list_view = device.find(
                    resourceId=self.ResourceID.LIST,
                )
                if list_view.exists():
                    list_view.scroll(Direction.DOWN)
                else:
                    logger.info("Cannot find list view to scroll. Finish.")
                    return
            else:
                # Check if we've reached the end of the least interacted list
                # Instagram typically shows only about 50 accounts in this category
                logger.info(
                    "Reached the end of least interacted accounts list, finish.",
                    extra={"color": f"{Fore.GREEN}"},
                )
                return