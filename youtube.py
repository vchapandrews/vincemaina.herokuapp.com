from __future__ import print_function

from googleapiclient.discovery import build
from requests import HTTPError

from models import Videos, db
from config import YOUTUBE_API_KEY

import os

youtube_api_key = YOUTUBE_API_KEY # Currently unrestricted - consider restricting. Don't keep this in this file. Look into using environment variables for secret keys.
youtube = build('youtube', 'v3', developerKey=youtube_api_key)

channel_id = 'UCn2iypP7ektcWULuNKGdcSQ'
uploads_id = channel_id[0] + 'U' + channel_id[2:]

def fetch_upload_ids():
    # Produces a list of IDs for each video the channel has uploaded
    keep_looping = True
    page_token = None
    video_id_list = []

    while keep_looping:

        request = youtube.playlistItems().list(
            part="contentDetails",
            maxResults=50, # This is the maximum value
            pageToken=page_token,
            playlistId=uploads_id
            )

        try:
            response = request.execute()
        except HTTPError as e:
            print('Error response status code : {0}, reason : {1}'.format(e.status_code, e.error_details))

        for item in response['items']:
            video_id_list.append(item['contentDetails']['videoId'])

        try:
            page_token = response['nextPageToken']
        except KeyError:
            print('No more pages!')
            keep_looping = False
    
    return video_id_list

def process_description(video_description, search_key):
    
    delimiter = '|'
    temp = None

    for i in video_description.splitlines():
        if search_key + ':' in i:
            temp = i[len(search_key) + 1:].strip()
            temp = [i.strip() for i in temp.split(delimiter)] 
            if search_key == ('Beat name'):
                temp = temp[0]
               
    return str(temp)

def add_uploads_to_database():
    video_id_list = fetch_upload_ids()
    keep_looping = True
    while keep_looping:
        if len(video_id_list) < 50:
            request = youtube.videos().list(
                    part="snippet,contentDetails",
                    id=video_id_list[0:len(video_id_list)]
                )
            keep_looping = False
        else:
            request = youtube.videos().list(
                    part="snippet,contentDetails",
                    id=video_id_list[0:50]
                )
            video_id_list = video_id_list[50:]

        try:
            response = request.execute()
        except HTTPError as e:
            print('Error response status code : {0}, reason : {1}'.format(e.status_code, e.error_details))

        # This takes those details and adds them to our database.

        for video in response['items']:
            video_to_add = Videos(
                video_id = video['id'],
                video_title = video['snippet']['title'],
                video_publishedAt = video['snippet']['publishedAt'],
                video_thumbnail = video['snippet']['thumbnails']['medium']['url'],
                video_description = video['snippet']['description'],
                video_beat_name = process_description(video['snippet']['description'], 'Beat name'),
                video_tags = process_description(video['snippet']['description'], 'Tags')
                )
            db.session.add(video_to_add)

    db.session.commit()