# As2 by RuiZhong
# SU ID: 330055594
# In this assignment, I mainly completed the generation of social network diagrams,
# used the interface of Twitter api, and transformed the crawl function in cookbook, captured reciprocal friends,
# and drawn social network diagrams based on this.

import twitter
import flask
from functools import partial
from sys import maxsize as maxint
import sys
import time
from urllib.error import URLError
from http.client import BadStatusLine
# import pymongo
import json
import networkx as nx
import matplotlib.pyplot as plt


# From Cookbook Example 1. Accessing Twitter's API for development purposes
def oauth_login():
    # XXX: Go to http://twitter.com/apps/new to create an app and get values
    # for these credentials that you'll need to provide in place of these
    # empty string values that are defined as placeholders.
    # See https://developer.twitter.com/en/docs/basics/authentication/overview/oauth
    # for more information on Twitter's OAuth implementation.

    CONSUMER_KEY = 'xdk58AbZdsALAYCtFX5yegjxH'
    CONSUMER_SECRET = 'QycXor19Bzgham9xDXMxlcLi0hNyfnR62pHrKCwxJLbngfYTVO'
    OAUTH_TOKEN = '1230489412578037760-PTj7tViWxbxjpSZk5S769Ew7XjZGfq'
    OAUTH_TOKEN_SECRET = 'odvj0fn3UbF2JFV9RWhaLeg8Oq2p66VrGgLSAJvTXU4pX'

    auth = twitter.oauth.OAuth(OAUTH_TOKEN, OAUTH_TOKEN_SECRET,
                               CONSUMER_KEY, CONSUMER_SECRET)

    twitter_api = twitter.Twitter(auth=auth)
    return twitter_api


# From Cookbook Example 16. Making robust Twitter requests
def make_twitter_request(twitter_api_func, max_errors=10, *args, **kw):
    # A nested helper function that handles common HTTPErrors. Return an updated
    # value for wait_period if the problem is a 500 level error. Block until the
    # rate limit is reset if it's a rate limiting issue (429 error). Returns None
    # for 401 and 404 errors, which requires special handling by the caller.
    def handle_twitter_http_error(e, wait_period=2, sleep_when_rate_limited=True):

        if wait_period > 3600:  # Seconds
            print('Too many retries. Quitting.', file=sys.stderr)
            raise e

        # See https://developer.twitter.com/en/docs/basics/response-codes
        # for common codes

        if e.e.code == 401:
            print('Encountered 401 Error (Not Authorized)', file=sys.stderr)
            return None
        elif e.e.code == 404:
            print('Encountered 404 Error (Not Found)', file=sys.stderr)
            return None
        elif e.e.code == 429:
            print('Encountered 429 Error (Rate Limit Exceeded)', file=sys.stderr)
            if sleep_when_rate_limited:
                print("Retrying in 15 minutes...ZzZ...", file=sys.stderr)
                sys.stderr.flush()
                time.sleep(60 * 15 + 5)
                print('...ZzZ...Awake now and trying again.', file=sys.stderr)
                return 2
            else:
                raise e  # Caller must handle the rate limiting issue
        elif e.e.code in (500, 502, 503, 504):
            print('Encountered {0} Error. Retrying in {1} seconds'.format(e.e.code, wait_period), file=sys.stderr)
            time.sleep(wait_period)
            wait_period *= 1.5
            return wait_period
        else:
            raise e

    # End of nested helper function

    wait_period = 2
    error_count = 0

    while True:
        try:
            return twitter_api_func(*args, **kw)
        except twitter.api.TwitterHTTPError as e:
            error_count = 0
            wait_period = handle_twitter_http_error(e, wait_period)
            if wait_period is None:
                return
        except URLError as e:
            error_count += 1
            time.sleep(wait_period)
            wait_period *= 1.5
            print("URLError encountered. Continuing.", file=sys.stderr)
            if error_count > max_errors:
                print("Too many consecutive errors...bailing out.", file=sys.stderr)
                raise
        except BadStatusLine as e:
            error_count += 1
            time.sleep(wait_period)
            wait_period *= 1.5
            print("BadStatusLine encountered. Continuing.", file=sys.stderr)
            if error_count > max_errors:
                print("Too many consecutive errors...bailing out.", file=sys.stderr)
                raise


# From Cookbook Example 19. Getting all friends or followers for a user
def get_friends_followers_ids(twitter_api, screen_name=None, user_id=None,
                              friends_limit=maxint, followers_limit=maxint):
    # Must have either screen_name or user_id (logical xor)
    assert (screen_name != None) != (user_id != None), "Must have screen_name or user_id, but not both"

    # See http://bit.ly/2GcjKJP and http://bit.ly/2rFz90N for details
    # on API parameters

    get_friends_ids = partial(make_twitter_request, twitter_api.friends.ids,
                              count=5000)
    get_followers_ids = partial(make_twitter_request, twitter_api.followers.ids,
                                count=5000)

    friends_ids, followers_ids = [], []

    for twitter_api_func, limit, ids, label in [
        [get_friends_ids, friends_limit, friends_ids, "friends"],
        [get_followers_ids, followers_limit, followers_ids, "followers"]
    ]:

        if limit == 0: continue

        cursor = -1
        while cursor != 0:

            # Use make_twitter_request via the partially bound callable...
            if screen_name:
                response = twitter_api_func(screen_name=screen_name, cursor=cursor)
            else:  # user_id
                response = twitter_api_func(user_id=user_id, cursor=cursor)

            if response is not None:
                ids += response['ids']
                cursor = response['next_cursor']

            print('Fetched {0} total {1} ids for {2}'.format(len(ids), label, (user_id or screen_name)),
                  file=sys.stderr)

            # XXX: You may want to store data during each iteration to provide an
            # an additional layer of protection from exceptional circumstances

            if len(ids) >= limit or response is None:
                break

    # Do something useful with the IDs, like store them to disk...
    return friends_ids[:friends_limit], followers_ids[:followers_limit]


# From Cookbook Example 17. Resolving user profile information
def get_user_profile(twitter_api, screen_names=None, user_ids=None):
    # Must have either screen_name or user_id (logical xor)
    assert (screen_names != None) != (user_ids != None), "Must have screen_names or user_ids, but not both"

    items_to_info = {}

    items = screen_names or user_ids

    while len(items) > 0:

        # Process 100 items at a time per the API specifications for /users/lookup.
        # See http://bit.ly/2Gcjfzr for details.

        items_str = ','.join([str(item) for item in items[:100]])
        items = items[100:]

        if screen_names:
            response = make_twitter_request(twitter_api.users.lookup,
                                            screen_name=items_str)
        else:  # user_ids
            response = make_twitter_request(twitter_api.users.lookup,
                                            user_id=items_str)

        for user_info in response:
            if screen_names:
                items_to_info[user_info['screen_name']] = user_info
            else:  # user_ids
                items_to_info[user_info['id']] = user_info

    return items_to_info


# From Cookbook Example 7. Saving and accessing JSON data with MongoDB
# def save_to_mongo(data, mongo_db, mongo_db_coll, **mongo_conn_kw):
#     # Connects to the MongoDB server running on
#     # localhost:27017 by default
#
#     client = pymongo.MongoClient(**mongo_conn_kw)
#
#     # Get a reference to a particular database
#
#     db = client[mongo_db]
#
#     # Reference a particular collection in the database
#
#     coll = db[mongo_db_coll]
#
#     # Perform a bulk insert and  return the IDs
#     try:
#         return coll.insert_many(data)
#     except:
#         return coll.insert_one(data)


# From Cookbook Crawling a friendship graph
# I changed the function to crawl reciprocal friends which are most popular in top 5
def crawl_followers(twitter_api, screen_name, limit=1000000, depth=2, **mongo_conn_kw):
    # Resolve the ID for screen_name and start working with IDs for consistency
    # in storage

    # start point
    seed_id = str(twitter_api.users.show(screen_name=screen_name)['id'])
    # Create graph
    G = nx.Graph()
    # Store the print color for nodes
    # n_color = []
    # Add start point node
    G.add_node(seed_id)  # use the id to identify nodes
    # n_color.append('red')

    # Request
    friends_ids, followers_ids = get_friends_followers_ids(twitter_api,
                                                           user_id=seed_id,
                                                           friends_limit=5000,
                                                           followers_limit=5000)
    # get reciprocal friends
    reciprocal_friends = set(friends_ids) & set(followers_ids)
    print("The reciprocal friends set is:", reciprocal_friends)
    print("The length of reciprocal friends set is:", len(reciprocal_friends))

    # find TOP5
    followers_count_ids = []
    followers_count_list = []
    for ids in reciprocal_friends:
        items_to_info = get_user_profile(twitter_api, user_ids=[ids])
        followers_count_ids.append(ids)
        # extract the followers_count parameter
        followers_count_list.append(items_to_info[ids]['followers_count'])
        # print(items_to_info[ids]['followers_count'])
    followers_dict = dict(zip(followers_count_ids, followers_count_list))
    # print(followers_dict)
    # sort
    followers_dict = sorted(followers_dict.items(), key=lambda item: item[1], reverse=True)
    # print(followers_dict)
    # extract top 5
    result_dict = followers_dict[0:5]
    next_queue = []
    for i in range(5):
        next_queue.append(result_dict[i][0])  # ids

    # Add reciprocal friends nodes
    G.add_nodes_from([x for x in next_queue])
    G.add_edges_from([(seed_id, y) for y in next_queue])

    # save_to_mongo({'reciprocal_friends': [_id for _id in next_queue]}, 'reciprocal_friends_crawl',
    #               '{0}-reciprocal_friends_ids'.format(seed_id), **mongo_conn_kw)
    # print("The next_queue is: ", next_queue)

    d = 1
    while d < depth:
        d += 1
        (queue, next_queue) = (next_queue, [])
        for fid in queue:
            # _, follower_ids = get_friends_followers_ids(twitter_api, user_id=fid,
            #                                             friends_limit=0,
            #                                             followers_limit=limit)
            friends_ids, followers_ids = get_friends_followers_ids(twitter_api,
                                                                   user_id=fid,
                                                                   friends_limit=5000,
                                                                   followers_limit=5000)

            reciprocal_friends = set(friends_ids) & set(followers_ids)
            print("The reciprocal friends set is:", reciprocal_friends)
            print("The length of reciprocal friends set is:", len(reciprocal_friends))
            followers_count_ids = []
            followers_count_list = []
            try:
                for ids in reciprocal_friends:
                    print("Now, the number of node is：", G.number_of_nodes())
                    print("The searching id is：", ids)
                    items_to_info = get_user_profile(twitter_api, user_ids=[ids])
                    followers_count_ids.append(ids)
                    followers_count_list.append(items_to_info[ids]['followers_count'])
                    # print(items_to_info[ids]['followers_count'])
                followers_dict = dict(zip(followers_count_ids, followers_count_list))
                # sort
                followers_dict = sorted(followers_dict.items(), key=lambda item: item[1], reverse=True)
                # extract top 5
                result_dict = followers_dict[0:5]
                friends_crawl_ids = []
            except:
                pass

            # corner case: when set length < 5, append the real length rather than 5.
            if len(reciprocal_friends) > 0:
                if len(reciprocal_friends) < 5:
                    final = len(reciprocal_friends)
                    for i in range(final):
                        friends_crawl_ids.append(result_dict[i][0])  # ids
                else:
                    for i in range(5):
                        friends_crawl_ids.append(result_dict[i][0])  # ids

            if len(reciprocal_friends) > 0:
                # Add nodes
                G.add_nodes_from([x for x in friends_crawl_ids])
                G.add_edges_from([(fid, y) for y in friends_crawl_ids])

            # Store a fid => follower_ids mapping in MongoDB
            # save_to_mongo({'reciprocal_friends': [_id for _id in friends_crawl_ids]},
            #               'reciprocal_friends_crawl', '{0}-reciprocal_friends_ids'.format(fid))

            next_queue += friends_crawl_ids

            if G.number_of_nodes() >= 100:
                print("\nFinish!")
                # console print
                print('The node number of this graph is:', G.number_of_nodes())
                print('The edge number of this graph is:', G.number_of_edges())
                # print diameter
                print('The diameter of this graph is:', nx.diameter(G))
                # print average length
                print('The average shortest path length of this graph is:', nx.average_shortest_path_length(G))
                # for i in range(G.number_of_nodes() - 1):
                #     n_color.append('blue')
                nx.draw(G, node_color='blue')
                plt.savefig("mygraph.png", bbox_inches='tight')
                plt.show()
                # file print
                f = open("output.txt", "w")
                print('The node number of this graph is:', G.number_of_nodes(), file=f)
                print('The edge number of this graph is:', G.number_of_edges(), file=f)
                # print diameter
                print('The diameter of this graph is:', nx.diameter(G), file=f)
                # print average length
                print('The average shortest path length of this graph is:', nx.average_shortest_path_length(G), file=f)
                return


if __name__ == "__main__":
    twitter_api = oauth_login()
    # print(twitter_api)
    # print(flask.__version__)
    # # SethDavisHoops
    # response = make_twitter_request(twitter_api.users.lookup,
    #                                 screen_name="SethDavisHoops")
    # # print(json.dumps(response, indent=1))
    # friends_ids, followers_ids = get_friends_followers_ids(twitter_api,
    #                                                        screen_name="SethDavisHoops",
    #                                                        friends_limit=5000,
    #                                                        followers_limit=5000)
    # reciprocal_friends = []
    # reciprocal_friends = set(friends_ids) & set(followers_ids)
    # print(friends_ids)
    # print(followers_ids)
    # print(reciprocal_friends)
    #
    # items_to_info = {}

    # followers_dict = {}
    # followers_count_ids = []
    # followers_count_list = []
    # for ids in reciprocal_friends:
    #     items_to_info = get_user_profile(twitter_api, user_ids=[ids])
    #     followers_count_ids.append(ids)
    #     followers_count_list.append(items_to_info[ids]['followers_count'])
    #     # print(items_to_info[ids]['followers_count'])
    # followers_dict = dict(zip(followers_count_ids, followers_count_list))
    # print(followers_dict)

    # followers_dict = sorted(followers_dict.items(), key=lambda item: item[1], reverse=True)
    # print(followers_dict)

    # result_dict = followers_dict[0:5]
    # print(result_dict)
    #
    # for i in range(5):
    #     print(result_dict[i][0])  # ids
    #     print(result_dict[i][1])  # counts

    crawl_followers(twitter_api, 'SethDavisHoops', depth=4, limit=5000, host='mongodb://localhost:27017')
