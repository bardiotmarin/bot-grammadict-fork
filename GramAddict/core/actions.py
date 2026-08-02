import logging
import re

from GramAddict.core.device_facade import DeviceFacade, Direction, Timeout
from GramAddict.core.utils import ActionBlockedError, random_sleep

logger = logging.getLogger(__name__)

# Wording Instagram uses when it throttles or blocks an action.
BLOCK_PHRASES = (
    "Action Blocked",
    "Action bloquée",
    "Try Again Later",
    "Réessayez plus tard",
    "We restrict certain activity",
    "Nous limitons certaines activités",
    "You've been blocked from",
)


class UniversalActions:
    def __init__(self, device: DeviceFacade):
        self.device = device

    @staticmethod
    def detect_block(device: DeviceFacade) -> bool:
        """Raise ActionBlockedError when Instagram shows its 'action blocked' dialog."""
        pattern = "|".join(re.escape(p) for p in BLOCK_PHRASES)
        dialog = device.find(textMatches=f"(?i).*({pattern}).*")
        if not dialog.exists():
            return False
        try:
            message = dialog.get_text()
        except Exception:
            message = "unknown"
        logger.error(f"Instagram is blocking our actions: '{message}'.")
        raise ActionBlockedError(
            f"Instagram has blocked the current action: '{message}'. Stopping to stay safe."
        )

    def search_text(self, text: str) -> bool:
        """Type `text` into the search field of a follow list. True when the field was usable."""
        search_field = self.device.find(className="android.widget.EditText")
        if not search_field.exists(Timeout.MEDIUM):
            logger.warning("No search field found on this list.")
            return False
        search_field.click()
        random_sleep(1, 2, modulable=False)
        search_field.set_text(text)
        random_sleep(1, 2, modulable=False)
        return True

    @staticmethod
    def close_keyboard(device: DeviceFacade):
        focused_textfield = device.find(focused=True, className="android.widget.EditText")
        if focused_textfield.exists(0):
            # Don't press Back if the focused field is the Instagram search bar
            # Pressing Back there would exit the search screen entirely
            try:
                res_id = focused_textfield.viewV2.info.get("resourceName", "") or ""
            except Exception:
                res_id = ""
            if "action_bar_search_edit_text" in res_id:
                logger.debug("Search bar is focused - NOT closing keyboard to preserve search screen.")
                return
            logger.info("Text field is focused, closing keyboard.")
            device.back()

    def _swipe_points(self, direction: Direction, delta_x=0, delta_y=0, start_point_x=0, start_point_y=0):
        # Precise swipe helper supporting custom start points and directions
        display_info = self.device.get_info()
        width = display_info['displayWidth']
        height = display_info['displayHeight']
        sx = start_point_x if start_point_x else width / 2
        sy = start_point_y if start_point_y else height / 2

        if direction == Direction.DOWN:
            # Swipe up to scroll down
            self.device.swipe_points(sx, sy, sx, sy - delta_y)
        elif direction == Direction.UP:
            # Swipe down to scroll up
            self.device.swipe_points(sx, sy, sx, sy + delta_y)
        elif direction == Direction.LEFT:
            ex = sx - delta_x if delta_x else width * 0.2
            self.device.swipe_points(sx, sy, ex, sy)
        elif direction == Direction.RIGHT:
            ex = sx + delta_x if delta_x else width * 0.8
            self.device.swipe_points(sx, sy, ex, sy)
        else:
            self.device.swipe(direction)

    def _reload_page(self):
        logger.info("Reload page..")
        self.device.swipe(Direction.DOWN, 0.85)
