import sys
import yaml
if len(sys.argv) != 2:
    sys.exit("Usage : python test_config.py accounts/<compte>/config.yml")
sys.argv = ['run.py', '--config', sys.argv[1]]

# Let's just use GramAddict
sys.path.insert(0, ".")
from GramAddict.core.config import Config
config = Config()
print("HASHTAG_POSTS_TOP:", repr(config.args.hashtag_posts_top))

for s in config.args.hashtag_posts_top:
    print(f"VAL: '{s}' (len: {len(s)})")

