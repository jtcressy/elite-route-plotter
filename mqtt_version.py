import functools
import signal

from Adafruit_IO import MQTTClient
import logging
import json

from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.sg.scripts import TOKENS_FILE
from xbox.sg.console import Console
from xbox.sg.enum import ConnectionState
from xbox.sg.manager import TextManager

import os
import sys


ADAFRUIT_IO_KEY = os.environ.get("ADAFRUIT_IO_KEY")
ADAFRUIT_IO_USERNAME = os.environ.get("ADAFRUIT_IO_USERNAME")
FEED_ID = os.environ.get("FEED_ID")
TOKENS_FILE = os.environ.get("TOKENS_FILE")
XBOX_IP = os.environ.get("XBOX_IP", None)
XBOX_EMAIL = os.environ.get("XBOX_EMAIL")
XBOX_PASSWORD = os.environ.get("XBOX_PASSWORD")


# Define callback functions which will be called when certain events happen.
def mqtt_connected(client):
    # Connected function will be called when the client is connected to Adafruit IO.
    # This is a good place to subscribe to feed changes.  The client parameter
    # passed to this function is the Adafruit IO MQTT client so you can make
    # calls against it easily.
    print('Connected to Adafruit IO!  Listening for {0} changes...'.format(FEED_ID))
    # Subscribe to changes on a feed named DemoFeed.
    client.subscribe(FEED_ID)


def mqtt_disconnected(client):
    # Disconnected function will be called when the client disconnects.
    print('Disconnected from Adafruit IO!')
    sys.exit(1)


def mqtt_message(console, client, feed_id, payload):
    data = json.loads(payload)
    logging.debug("got {} from mqtt".format(data))
    if data["event"] == "send_text":
        console.send_systemtext_input(data["text"])
        console.finish_text_input()


def xbox_on_text_config(payload):
    pass


def xbox_on_text_input(console, client: MQTTClient, payload):
    # client.publish(FEED_ID, value="on_text_input")
    output = json.dumps({"event": "on_text_input", "text": payload["text_chunk"]})
    client.publish(FEED_ID, value=output)
    logging.debug("Sending {}".format(output))


def xbox_on_text_done(payload):
    pass


def xbox_on_timeout(console):
    print('Connection Timedout')


def main():
    logging.basicConfig(level=logging.DEBUG)
    tokens_loaded = False
    try:
        auth_mgr = AuthenticationManager()
        if TOKENS_FILE:
            try:
                auth_mgr.load(TOKENS_FILE)
                tokens_loaded = True
            except FileNotFoundError as e:
                print("Failed to load tokens from 'TOKENS_FILE', trying user/pass. Error: {}".format(e.strerror))
        auth_mgr.email_address = XBOX_EMAIL
        auth_mgr.password = XBOX_PASSWORD
        auth_mgr.authenticate(do_refresh=True)
        if TOKENS_FILE:
            auth_mgr.dump(TOKENS_FILE)
    except Exception as e:
        print("Failed to auth with provided credentials, Error: %s" % e)
        print("Please re-run xbox-authenticate to get a fresh set of tokens")
        sys.exit(1)

    userhash = auth_mgr.userinfo.userhash
    token = auth_mgr.xsts_token.jwt
    print(userhash, token)
    discovered = Console.discover(timeout=1, addr=XBOX_IP)
    if len(discovered):
        console = discovered[0]
        console.on_timeout += xbox_on_timeout
        console.add_manager(TextManager)

        client = MQTTClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)
        client.on_connect = mqtt_connected
        client.on_disconnect = mqtt_disconnected
        client.on_message = functools.partial(mqtt_message, console)

        console.text.on_systemtext_configuration += xbox_on_text_config
        console.text.on_systemtext_input += functools.partial(xbox_on_text_input, console, client)
        console.text.on_systemtext_done += xbox_on_text_done
        while True:
            state = None
            try:
                state = console.connect(userhash, token)
            except Exception as e:
                print(e)
            if state == ConnectionState.Connected:
                break
        console.wait(1)

        signal.signal(signal.SIGINT, lambda *args: console.protocol.stop())

        if not client.is_connected():
            client.connect()

        client.loop_background()

        console.protocol.serve_forever()
    else:
        print("No consoles discovered")
        sys.exit(1)


if __name__ == "__main__":
    main()
