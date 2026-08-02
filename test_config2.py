import configargparse
import yaml

with open('test_short.yml', 'w') as f:
    f.write('hashtag-posts-top: [dj,ddj,ableton]\n')

parser = configargparse.ArgumentParser(default_config_files=['test_short.yml'])
parser.add_argument('--hashtag-posts-top', nargs='+', default=None)

options, _ = parser.parse_known_args()
print("SHORT:", options.hashtag_posts_top)

with open('test_long.yml', 'w') as f:
    long_list = "[dj,ddj,ableton,afrohouse,techno,housemusic,techhouse,deephouse,soulfulhouse,techhousemusic,housevibes,afrohousemusic,afrotech,edm,dance,electronicmusic,clubmusic,festivalvibes,undergroundhouse,housebeats,edmfamily,partytime,djslife,vinylhouse,electronicdance,musicproducer,tracklist,remix,bpm,festival,groove,dancefloor,housegroove,percussive,afrocentric,danceparty,musicfestival,groovehouse,beats,musiclovers,soundcloudmusic,electronicvibes,edmcommunity,technohouse,deeptech,housefan,technoaddict,musicfans,electronicartist,partyvibes,futurehouse,basshouse,minimaltechno,melodictechno,tropicalhouse,basslinehouse,globalbeats,cosmictechno,rhythmhouse,musicproducerlife,beatslovers,dancecommunity,vibecheck,technoDJ,electronicbeats,ableton,serato,edmproduction,djlife,housemusicdaily,deeptechno,technohousemusic,edmfans,clubvibes,edmlove,housejams,afrobeatmusic,edmvibes,techhousegroove,dancevibes,vinyltechno,housebeatslove,technoartists,festivalfun,electronicdancevibes,technoaddicted,musicproducercommunity,remixlove,bpmvibes,festivallove,groovemusic,housegroovebeats,percussivegroove,afrocentricmusic,dancepartylife,musicfestivalvibes,groovemusiclove,beatscommunity,musicloversunite,electronicbeatslove,edmcommunityvibes,deeptechhouse,house,musicfanlife]"
    f.write(f'hashtag-posts-top:\n  {long_list}\n')

parser2 = configargparse.ArgumentParser(default_config_files=['test_long.yml'])
parser2.add_argument('--hashtag-posts-top', nargs='+', default=None)

options2, _ = parser2.parse_known_args()
print("LONG:", options2.hashtag_posts_top)
