import configargparse
import yaml

with open('test_list.yml', 'w') as f:
    long_list = """hashtag-posts-top:
  - dj
  - ddj
  - ableton
  - afrohouse
  - techno
  - housemusic
  - techhouse
  - deephouse
  - soulfulhouse
  - techhousemusic
  - housevibes
  - afrohousemusic
  - afrotech
  - edm
  - dance
  - electronicmusic
  - clubmusic
  - festivalvibes
  - undergroundhouse
"""
    f.write(long_list)

parser2 = configargparse.ArgumentParser(default_config_files=['test_list.yml'])
parser2.add_argument('--hashtag-posts-top', nargs='+', default=None)

options2, _ = parser2.parse_known_args()
print("LIST:", options2.hashtag_posts_top)
