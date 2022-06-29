from __future__ import print_function
import io

import json

from datetime import datetime
from random import randint

from flask import redirect, render_template, url_for, request
from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment
from paypalcheckoutsdk.orders import (OrdersCaptureRequest,
                                      OrdersCreateRequest, OrdersGetRequest)
from paypalhttp import HttpError

from googleapiclient.errors import HttpError

'''-------------------------------------------------------------
MY MODULES'''

from config import app, db, local_address, live_address, lease_price, PAYPAL_SANDBOX_CLIENT_ID, PAYPAL_SANDBOX_CLIENT_SECRET

from models import Videos, clear_database
from youtube import add_uploads_to_database

from mail import send_confirmation_email
from drive import fetch_beat_files, download_all_files, return_directory, start_folder_id

from docs import export_lease, create_lease

domain = live_address
if __name__ == '__main__':
    domain = local_address

'''----------------------------------------------------------------------------------------------------
ROUTING'''

@app.route('/home')
def home():
    return redirect(url_for('beat_library'))

@app.route('/') # START PAGE
@app.route('/beats')
def beat_library():
    videos = Videos.query.all() # Consider updating this to only send through the data from 'videos' that is needed. Better to be more specific, in case I add any kind of sensitive information to this database model in future.
    return render_template('beat-library.html', videos=videos)

@app.route('/beats/<video_id>')
def beat(video_id):
    video = Videos.query.get(video_id)
    return render_template('beat.html', video=video)

@app.route('/fetchvideos', methods=['GET', 'POST'])
def update_database():

    if request.method == 'POST':
        clear_database()

        add_uploads_to_database()

        beat_folder_id = return_directory(start_folder_id)
        for i in dict.keys(beat_folder_id):
            if 'Mixdown' in return_directory(beat_folder_id[i]):
                try:
                    video = Videos.query.filter_by(video_beat_name=i).first()
                    video.beat_mixdowns = return_directory(beat_folder_id[i])['Mixdown']
                    db.session.commit()
                except:
                    db.session.rollback()
                    print('Error 1: Video not in database. Or other error.')
            if 'Stems' in return_directory(beat_folder_id[i]):
                try:
                    video = Videos.query.filter_by(video_beat_name=i).first()
                    video.beat_stems = return_directory(beat_folder_id[i])['Stems']
                    db.session.commit()
                except:
                    db.session.rollback()
                    print('Error 2: Video not in database. Or other error.')
  
    videos = Videos.query.all()
    return render_template('update_database.html', videos=videos)


'''-------------------------------------------------------------------------------------------------------------------
PAYPAL API - ACCEPTING PAYMENTS'''

# Creating an environment
environment = SandboxEnvironment(
    client_id=PAYPAL_SANDBOX_CLIENT_ID,
    client_secret=PAYPAL_SANDBOX_CLIENT_SECRET
    )
client = PayPalHttpClient(environment)

@app.route('/beats/<video_id>/<video_title>/purchase')
def create_order(video_id, video_title):

    reference_id = str(datetime.utcnow()) + str(randint(0,1000))

    request = OrdersCreateRequest()

    request.prefer('return=representation')

    request.request_body (
        {
            'intent' : 'CAPTURE',
            'purchase_units': [
                {
                    'description': video_title, # CHANGE THIS TO YOUTUBE VIDEO TITLE
                    'custom_id': video_id, # CHANGE THIS TO YOUTUBE VIDEO ID
                    'reference_id': reference_id,
                    'soft_descriptor': 'Vince Maina', # THIS IS WHAT SHOWS IN BANK STATEMENT: 'PAYPAL *Vince Maina'
                    'amount': {
                        'currency_code': 'GBP',
                        'value': lease_price
                    }
                }
            ],
            'application_context': {
                'brand_name': 'Vince Maina',
                'cancel_url': domain + '/beats/' + video_id, # FIX THIS
                'return_url': domain + '/confirming', # Basically this should forward the user to a payment confirmation page where they can access their files and lease document.
                'user_action': 'PAY_NOW'
            }
        }
    )

    # Executes request
    try:
        response = client.execute(request)

        order_id = response.result.id
        print('\nOrder ID:', order_id, '\n')

        # Fetches approval link. Have used this approach in case the approval link is not the second link returned.
        if response.result.links[1]['rel'] == 'approve':
            approve_link = response.result.links[1]['href']
        else:
            print('False') # Add for loop here to iterate through all links until it finds the approve link.

        # CUSTOMER APPROVES TRANSACTION
        return redirect(approve_link)

    except IOError as ioe:
        print('EXCEPTION\n', ioe)
        if isinstance(ioe, HttpError):
            # Something went wrong server-side
            print(ioe.status_code)

@app.route('/confirming', methods=['GET', 'POST'])
def capture_order():

    from flask import request  # Check if there's a way I can do this without having to import this package here inside the function
    url = request.url

    order_id = [i.split('=') for i in url[url.find('?') + 1:].split('&')][0][1]

    if request.method == 'POST':

        artists_legal_name = request.form['artists_legal_name']
        artists_professional_name = request.form['artists_professional_name']

        try:

            capture_request = OrdersCaptureRequest(order_id) # This should be an Approved Order ID
            response = client.execute(capture_request)

            print(response)

            lease_id = create_lease(
                producers_legal_name='Vincent Chapman-Andrews',
                producers_professional_name='Vince Maina',
                artists_legal_name=artists_legal_name,
                artists_professional_name=artists_professional_name,
                beat_name='Maida Vale', # FIX
                youtube_link='https://www.youtube.com/watch?v=uBXpY1gE4xU&ab_channel=VinceMaina', # FIX
                composer_legal_name='Vincent Chapman-Andrews',
                beat_price='£' + lease_price # FIX - SHOULD MATCH WHAT IS IN THE PAYPAL ORDER RECIEPT.
            )

            return redirect(url_for('receipt', order_id=order_id, lease_id=lease_id))

        except IOError as ioe:
            if isinstance(ioe, HttpError):
                # Something went wrong server-side i.e. Paypal's end
                print(ioe.status_code)
                print(ioe.headers)
                print(ioe)
            else:
                # Something went wrong client side
                print(ioe)

            return redirect(url_for('error_payment_not_captured'))

    return render_template('lease_form.html')

@app.route('/<order_id>/<lease_id>/receipt', methods=['GET', 'POST'])
def receipt(order_id, lease_id):

    request = OrdersGetRequest(order_id)
    response = client.execute(request)

    video_id = response.result.purchase_units[0]['custom_id']
        
    video = Videos.query.get(video_id)
    video_beat_name = video.video_beat_name # SLICED because saved as string with dictionary syntax i.e. '['Beat_name']'

    stems, mixdowns = fetch_beat_files(video_beat_name)

    send_confirmation_email(
        order_id = order_id,
        beat_name = video_beat_name,
        video_title = video.video_title,
        recipient_address = 'vince@elevatecopy.com',
        lease_id = lease_id
    )

    from flask import request

    if request.method == 'POST':
        if request.form['submit'] == 'mixdowns':
            return download_all_files(video_beat_name, mixdowns, 'mixdowns')
        elif request.form['submit'] == 'stems':
            return download_all_files(video_beat_name, stems, 'stems')
        elif request.form['submit'] == 'lease':
            return export_lease(lease_id, 'testpath.pdf')
    else:

        return render_template('receipt.html', order_id=order_id, video=video, stems=stems, mixdowns=mixdowns)

'''----------------------------------------------------------------------------------------------------
ERRORS'''

@app.route('/error/001')
def error_payment_not_captured():
    return 'Error 001: Payment Unsuccessful. Please contact site owner.'

'''----------------------------------------------------------------------------------------------------
RUNS THE APP ON A LOCAL SERVER'''

if __name__ == '__main__':
    app.run(debug=True)