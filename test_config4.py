import configargparse

with open('test_split.yml', 'w') as f:
    long_list = """hashtag-posts-top:
  [dj,ddj,ableton,afrohouse,techno,housemusic,techhouse,deephouse,soulfulhouse,techhousemusic,housevibes,afrohousemusic,afrotech,edm,dance,electronicmusic,clubmusic,festivalvibes,undergroundhouse,housebeats,edmfamily,partytime,djslife,vinylhouse,electronicdance,musicproducer,tracklist,remix,bpm,festival,groove,dancefloor,housegroove,percussive,afrocentric,danceparty,musicfestival,groovehouse,beats,
   musiclovers,soundcloudmusic,electronicvibes,edmcommunity,technohouse,deeptech,housefan,technoaddict,musicfans,electronicartist,partyvibes,futurehouse,basshouse,minimaltechno,melodictechno,tropicalhouse,basslinehouse,globalbeats,cosmictechno,rhythmhouse,musicproducerlife,beatslovers,dancecommunity,vibecheck,technoDJ,electronicbeats,ableton,serato,edmproduction,djlife,housemusicdaily,deeptechno,
   technohousemusic,edmfans,clubvibes,edmlove,housejams,afrobeatmusic,edmvibes,techhousegroove,dancevibes,vinyltechno,housebeatslove,technoartists,festivalfun,electronicdancevibes,technoaddicted,musicproducercommunity,remixlove,bpmvibes,festivallove,groovemusic,housegroovebeats,percussivegroove,afrocentricmusic,dancepartylife,musicfestivalvibes,groovemusiclove,beatscommunity,musicloversunite,
   electronicbeatslove,edmcommunityvibes,deeptechhouse,house,musicfanlife]"""
    f.write(long_list)

parser2 = configargparse.ArgumentParser(default_config_files=['test_split.yml'])
parser2.add_argument('--hashtag-posts-top', nargs='+', default=None)

options2, _ = parser2.parse_known_args()
print("SPLIT:", options2.hashtag_posts_top)
