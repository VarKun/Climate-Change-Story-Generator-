from naoqi import ALProxy
import qi
import urllib2  # For urllib.request and urllib.urlopen in Python 2
import base64
import json
import urllib
import zmq
import time
import sys
import threading
import argparse
import re
import os

# Create a context
context = zmq.Context()
# Create a SUB socket (subscriber)
subscriber = context.socket(zmq.SUB)
subscriber.connect("tcp://localhost:5555")  # Connect to publisher
# Subscribe to all messages (using byte string in Python 2)
subscriber.setsockopt(zmq.SUBSCRIBE, b"")
local_image = "current.png"
local_txt = "current.txt"
# local_text = "next"

class myModule():
    def __init__(self, session, robot_ip, robot_port):
        self.tts = session.service("ALTextToSpeech")
        self.tts.setLanguage("English")
        self.tts.setParameter("speed", 80)
        self.asr_service = session.service("ALAnimatedSpeech")
        self.configuration = {"bodyLanguageMode":"contextual"}

        self.tablet_proxy = ALProxy("ALTabletService", robot_ip, robot_port)
        self.posture_proxy = ALProxy("ALRobotPosture", robot_ip, robot_port)

    def robot_speech(self):
        # Read the contents of the text file
        with open(local_txt, 'r') as file:
            text = file.read()
        # Regex to capture everything starting from '**Title:**'
        match = re.search(r"(\*\*Title:\*\*.*)", text, re.DOTALL)
        if match:
            text = match.group(1)
        print(text)
        self.asr_service.say("Here is the story")
        self.asr_service.say(str(text), self.configuration)
        self.posture_proxy.goToPosture("StandInit", 0.7)  # Speed factor 0.8

        
    def uploadPhotoToWeb(sel, photo):
        """We need to upload photo to the web since we (me) are not able to open it from the local folder."""
        with open(photo, "rb") as f:  # Open our image file as read-only in binary mode
            image_data = f.read()  # Read in our image file
            b64_image = base64.standard_b64encode(image_data)  # Encode the image to base64
        client_id = os.environ.get("IMGUR_CLIENT_ID")
        if not client_id:
            raise RuntimeError("IMGUR_CLIENT_ID is not set; cannot upload image to Imgur.")
        # This is to get the registration on the app and make it works with Pepper robot
        headers = {'Authorization': 'Client-ID ' + client_id}

        data = {'image': b64_image, 'title': 'test'}

        # Create the request and pass the data
        request = urllib2.Request(url="https://api.imgur.com/3/upload.json", data=urllib.urlencode(data), headers=headers)

        # Make the request and get the response
        response = urllib2.urlopen(request).read()
        parse = json.loads(response)

        return parse['data']['link']  # Returns a URL return to the photo before moving to the next step

    def robot_tablet(self):
        photo_link = self.uploadPhotoToWeb(local_image)
        print("-----photo_link", photo_link)
        self.tablet_proxy.showImage(str(photo_link))

    def run(self):
        # Receive and print messages
        try:
            while True:
                try:
                    # Create two threads
                    self.thread1 = threading.Thread(target=self.robot_speech)
                    self.thread2 = threading.Thread(target=self.robot_tablet)
                    message2 = subscriber.recv_string(flags=zmq.NOBLOCK) 
                    if (str(message2)):
                        print("receive message", message2, "and send back to FC1FC2: done")
                        # Start the threads
                        self.thread1.start()
                        self.thread2.start()
                        # Wait for both threads to complete
                        self.thread1.join()
                        self.thread2.join()
                        print("Robot action completed")

                except zmq.Again as e:
                    time.sleep(0.2)
        except KeyboardInterrupt:
            print("Interrupted by user, stopping HumanGreeter")
            sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", type=str, default=os.environ.get("PEPPER_ROBOT_IP", "127.0.0.1"),
                        help="Robot IP address. Override via --ip or set PEPPER_ROBOT_IP.")
    parser.add_argument("--port", type=int, default=9559,
                        help="Naoqi port number")

    args = parser.parse_args()
    session = qi.Session()
    ip = args.ip
    port = args.port
    try:
        session.connect("tcp://" + args.ip + ":" + str(args.port))
    except RuntimeError:
        print ("Can't connect to Naoqi at ip \"" + args.ip + "\" on port " + str(args.port) +".\n"
               "Please check your script arguments. Run with -h option for help.")
        sys.exit(1)
    action = myModule(session, ip, port)
    action.run()
    # action.robot_speech()
