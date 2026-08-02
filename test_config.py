import sys
import yaml
sys.argv = ['run.py', '--config', 'd:/automation/android_bot_automation_insta/accounts/mon_compte/config.yml']

# Let's just use GramAddict
sys.path.insert(0, ".")
from GramAddict.core.config import Config
config = Config()
print("HASHTAG_POSTS_TOP:", repr(config.args.hashtag_posts_top))

for s in config.args.hashtag_posts_top:
    print(f"VAL: '{s}' (len: {len(s)})")

