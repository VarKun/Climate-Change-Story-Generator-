from naoqi import ALProxy
import urllib2  # For urllib.request and urllib.urlopen in Python 2
import base64
import json
import urllib
import os
from dotenv import load_dotenv

load_dotenv()

local_file_path = "current.jpg"
# Robot details
robot_ip = os.environ.get("BUDDY_ROBOT_IP")
if not robot_ip:
    raise RuntimeError("BUDDY_ROBOT_IP is not set; please configure the robot IP in your environment.")

def uploadPhotoToWeb(photo):
    """We need to upload photo to the web since we (me) are not able to open it from the local folder."""
    with open(photo, "rb") as f:  # Open our image file as read-only in binary mode
        image_data = f.read()  # Read in our image file
        b64_image = base64.standard_b64encode(image_data)  # Encode the image to base64

    client_id = os.environ.get("IMGUR_CLIENT_ID")
    if not client_id:
        raise RuntimeError("IMGUR_CLIENT_ID is not set; cannot upload image to Imgur.")
    headers = {'Authorization': 'Client-ID ' + client_id}

    data = {'image': b64_image, 'title': 'test'}

    # Create the request and pass the data
    request = urllib2.Request(url="https://api.imgur.com/3/upload.json", data=urllib.urlencode(data), headers=headers)

    # Make the request and get the response
    response = urllib2.urlopen(request).read()
    parse = json.loads(response)

    return parse['data']['link']  # Returns a URL of the photo

# Upload the photo and print the URL
photo_link = uploadPhotoToWeb(local_file_path)
print(photo_link)

tablet_proxy = ALProxy("ALTabletService", robot_ip, 9559)
tablet_proxy.hideImage()
# result = tablet_proxy.showImage(str(photo_link))
# # tablet_proxy.showImage("http://<PEPPER_TABLET_IP>/img/help_charger.png")
# # result = tablet_proxy.showWebview("i.imgur.com/gCqnYVz.jpeg")
# print(result)
